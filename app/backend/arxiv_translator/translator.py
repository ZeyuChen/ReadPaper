"""
Gemini-based whole-file LaTeX translator.

Design: Send each .tex file in its entirety to Gemini 3.0 Flash (1M context window).
No text-node extraction, no batching, no delimiter splitting.
One file = one API call. Simple retry on failure.
"""

from google import genai
from google.genai import types
import asyncio
import os
import re
import random
from .logging_utils import logger


# ── Config ────────────────────────────────────────────────────────────────────

_MAX_RETRIES = 3
_API_TIMEOUT_MS = 300_000  # 5 minutes — generous for large files


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_markdown_fences(text: str) -> str:
    """Strip ```latex ... ``` wrapping if the model adds it."""
    m = re.search(r'^```(?:latex)?\s*(.*?)\s*```$', text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else text


async def _backoff_sleep(attempt: int) -> None:
    delay = (2 ** attempt) + random.random() * 2
    logger.info(f"Backoff: sleeping {delay:.1f}s (attempt {attempt})")
    await asyncio.sleep(delay)


# ── Main Translator Class ─────────────────────────────────────────────────────

class GeminiTranslator:

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1beta', 'timeout': _API_TIMEOUT_MS}
        )

        # Load prompt
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "whole_file_translation_prompt.txt"
        )
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read()
        else:
            logger.warning(f"Prompt not found at {prompt_path}, using minimal fallback.")
            self.system_prompt = (
                "You are a professional academic translator. "
                "Translate the following LaTeX file from English to Chinese. "
                "Output ONLY the translated LaTeX code, no markdown fences."
            )

    async def translate_file(
        self,
        content: str,
        filename: str = "file.tex",
    ) -> tuple[str, int, int]:
        """
        Translate an entire .tex file.

        Args:
            content: Full LaTeX file content (comments already stripped).
            filename: For logging purposes.

        Returns:
            (translated_content, input_tokens, output_tokens)

        On unrecoverable failure, returns the original content unchanged.
        """
        total_in, total_out = 0, 0

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.1,
                    ),
                    contents=[content],
                )

                # Extract token counts
                in_tok, out_tok = 0, 0
                um = getattr(response, 'usage_metadata', None)
                if um is not None:
                    in_tok = getattr(um, 'prompt_token_count', None) or 0
                    out_tok = getattr(um, 'candidates_token_count', None) or 0
                    if in_tok == 0 and out_tok == 0:
                        total_tok = getattr(um, 'total_token_count', None) or 0
                        if total_tok > 0:
                            in_tok = int(total_tok * 0.6)
                            out_tok = total_tok - in_tok
                total_in += in_tok
                total_out += out_tok

                # Get response text
                try:
                    resp_text = response.text or ""
                except (ValueError, AttributeError):
                    logger.warning(f"[{filename}] Response had no text (attempt {attempt})")
                    if attempt < _MAX_RETRIES:
                        await _backoff_sleep(attempt)
                        continue
                    return content, total_in, total_out

                # Strip markdown fences if present
                resp_text = _clean_markdown_fences(resp_text)

                # Basic sanity check: output shouldn't be empty or tiny
                if len(resp_text.strip()) < 20:
                    logger.warning(f"[{filename}] Response too short ({len(resp_text)} chars), attempt {attempt}")
                    if attempt < _MAX_RETRIES:
                        await _backoff_sleep(attempt)
                        continue
                    return content, total_in, total_out

                logger.info(
                    f"[{filename}] Translated OK — "
                    f"In: {in_tok:,} / Out: {out_tok:,} tokens, "
                    f"ratio: {len(resp_text)/max(len(content),1):.2f}"
                )
                return resp_text, total_in, total_out

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(k in err_str for k in ('429', 'rate', 'resource', 'quota'))
                logger.error(f"[{filename}] API error (attempt {attempt}/{_MAX_RETRIES}): {e}")
                if attempt < _MAX_RETRIES:
                    extra_delay = 5.0 if is_rate_limit else 0.0
                    await asyncio.sleep((2 ** attempt) + random.random() * 2 + extra_delay)
                    continue
                # Give up — return original content
                logger.error(f"[{filename}] All {_MAX_RETRIES} attempts failed, keeping original")
                return content, total_in, total_out

        # Should not reach here
        return content, total_in, total_out
