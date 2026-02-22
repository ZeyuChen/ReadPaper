"""
Phase 3: Gemini-based text-node translator — Robust Concurrent Edition.

Key design decisions:
- Conservative concurrency: MAX_BATCH_CONCURRENCY=4 per worker process.
  Combined with MAX_CONCURRENT_REQUESTS=2 file workers in main.py,
  the total peak is 2 × 4 = 8 simultaneous Gemini API calls.
- CRITICAL: Retry loops run OUTSIDE the semaphore to prevent deadlocks.
  The semaphore is acquired only for the duration of a single API call.
- Exponential backoff with jitter on API failures (up to 3 retries).
- Non-streaming API for more robust responses.
- Chunk size 8000 chars.
"""

from google import genai
from google.genai import types
import asyncio
import os
import re
import random
import time
from typing import List, Optional
from .logging_utils import logger
from .text_extractor import TextNode, split_into_paragraphs


# ── Config ────────────────────────────────────────────────────────────────────

_MAX_BATCH_CONCURRENCY = int(os.getenv("MAX_BATCH_CONCURRENCY", "4"))
_DEFAULT_CHUNK_CHARS = int(os.getenv("TRANSLATION_CHUNK_CHARS", "8000"))
_MAX_RETRIES = 5


# ── Validation helpers ────────────────────────────────────────────────────────

def _has_markdown_fences(text: str) -> bool:
    return bool(re.search(r'^```', text, re.MULTILINE))


def _clean_markdown_fences(text: str) -> str:
    m = re.search(r'^```(?:latex)?\s*(.*?)\s*```$', text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else text


def _strip_conversational_prefix(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith(':') and len(stripped) < 60 and i <= 2:
            continue
        return '\n'.join(lines[i:])
    return text


def _validate_translation(original: str, translated: str) -> bool:
    if not translated.strip():
        return False
    if _has_markdown_fences(translated):
        return False
    ratio = len(translated) / max(len(original), 1)
    # CJK translations can be much shorter (compact characters) or longer
    # (explicit parenthetical terms). Use generous bounds.
    if ratio < 0.05 or ratio > 8.0:
        logger.warning(f"Translation length ratio out of range: {ratio:.2f}")
        return False
    return True


async def _backoff_sleep(attempt: int, extra: float = 0.0) -> None:
    delay = (2 ** attempt) + random.random() + extra
    logger.info(f"Backoff: sleeping {delay:.1f}s (attempt {attempt})")
    await asyncio.sleep(delay)


# ── Main Translator Class ─────────────────────────────────────────────────────

class GeminiTranslator:

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1beta', 'timeout': 120000}
        )
        self._sync_client = self._client

        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        self.translation_prompt = self._load_prompt(
            os.path.join(prompt_dir, "translation_prompt.txt"),
            "You are a professional academic translator. Translate English to formal academic Chinese."
        )
        self.text_only_prompt = self._load_prompt(
            os.path.join(prompt_dir, "text_only_translation_prompt.txt"),
            self._default_text_only_prompt()
        )

    @staticmethod
    def _load_prompt(path: str, fallback: str) -> str:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        logger.warning(f"Prompt not found at {path}, using fallback.")
        return fallback

    @staticmethod
    def _default_text_only_prompt() -> str:
        return """You are a professional academic translator specializing in computer science and mathematics.

You will receive PURE ENGLISH PROSE TEXT extracted from a LaTeX paper.
There are NO LaTeX commands in the input — only human-readable sentences.

## YOUR TASK
Translate the input text from English to formal academic Chinese.

## RULES
1. Output ONLY the Chinese translation. No explanations, no preambles, no markdown.
2. Preserve paragraph breaks (blank lines) exactly as they appear.
3. Use formal, concise academic Chinese.
4. Keep English terms that are standard in the field (e.g., Transformer, BERT, softmax).
5. Add a space between Chinese characters and English words/numbers.

## EXAMPLES
Input:  We propose a novel attention mechanism that achieves state-of-the-art results.
Output: 我们提出了一种新颖的注意力机制，达到了最先进的结果。

Input:  The model achieves 95% accuracy on the benchmark dataset.
Output: 该模型在基准数据集上达到了 95% 的准确率。
"""

    # ── Single API call (acquires and releases semaphore for just the call) ────

    async def _call_gemini(
        self,
        text: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[str, int, int]:
        """
        Make ONE Gemini API call, guarded by semaphore.
        Returns (response_text, in_tokens, out_tokens).
        Raises on any API error — caller handles retries.
        """
        async with semaphore:
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=self.text_only_prompt,
                    temperature=0.1,
                ),
                contents=[text]
            )

        # Extract tokens (outside semaphore — no need to hold it)
        in_tok, out_tok = 0, 0
        um = getattr(response, 'usage_metadata', None)
        if um is not None:
            in_tok = getattr(um, 'prompt_token_count', None) or 0
            out_tok = getattr(um, 'candidates_token_count', None) or 0
            # Fallback: if individual counts are missing, use total_token_count
            if in_tok == 0 and out_tok == 0:
                total_tok = getattr(um, 'total_token_count', None) or 0
                if total_tok > 0:
                    # Split heuristically: attribute 60% to input, 40% to output
                    in_tok = int(total_tok * 0.6)
                    out_tok = total_tok - in_tok
            logger.debug(f"Token counts — in: {in_tok}, out: {out_tok}")

        # Safely get text
        try:
            resp_text = response.text or ""
        except (ValueError, AttributeError):
            logger.warning("Response had no text (possibly blocked)")
            resp_text = ""

        return resp_text, in_tok, out_tok

    # ── Batch translation with retry loop OUTSIDE semaphore ────────────────────

    async def _async_translate_chunk(
        self,
        nodes: List[TextNode],
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, int, int]:
        """
        Translate a batch of TextNodes. Retries are outside the semaphore.
        Returns (failed_count, in_tokens, out_tokens).
        """
        DELIMITER = "\n\n---NODE_BREAK---\n\n"
        batch_text = DELIMITER.join(n.text for n in nodes)
        total_in, total_out = 0, 0

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp_text, in_tok, out_tok = await self._call_gemini(batch_text, semaphore)
                total_in += in_tok
                total_out += out_tok

                resp_text = _clean_markdown_fences(resp_text)
                resp_text = _strip_conversational_prefix(resp_text)

                if not _validate_translation(batch_text, resp_text):
                    logger.warning(f"Batch validation failed (attempt {attempt}/{_MAX_RETRIES})")
                    if attempt < _MAX_RETRIES:
                        await _backoff_sleep(attempt)
                        continue  # retry — semaphore already released
                    # Final attempt failed — use originals
                    for node in nodes:
                        node.translated = node.text
                    return len(nodes), total_in, total_out

                # Try to split by delimiter
                parts = resp_text.split(DELIMITER)
                if len(parts) == len(nodes):
                    failed = 0
                    for node, translated_text in zip(nodes, parts):
                        if _validate_translation(node.text, translated_text):
                            node.translated = translated_text
                        else:
                            node.translated = node.text
                            failed += 1
                    return failed, total_in, total_out
                else:
                    logger.warning(
                        f"Delimiter mismatch: expected {len(nodes)}, got {len(parts)}. "
                        "Falling back to per-node translation."
                    )
                    # Per-node fallback — semaphore is NOT held, safe to call
                    f, i, o = await self._async_translate_nodes_individually(nodes, semaphore)
                    return f, total_in + i, total_out + o

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(k in err_str for k in ('429', 'rate', 'resource', 'quota'))
                logger.error(f"Batch failed (attempt {attempt}/{_MAX_RETRIES}): {e}")
                if attempt < _MAX_RETRIES:
                    extra = 3.0 if is_rate_limit else 0.0
                    await _backoff_sleep(attempt, extra)
                    continue  # retry — semaphore already released
                # Final attempt — use originals
                for node in nodes:
                    if not node.translated:
                        node.translated = node.text
                return len(nodes), total_in, total_out

        # Should not reach here, but just in case
        return len(nodes), total_in, total_out

    # ── Single node translation with retry loop OUTSIDE semaphore ─────────────

    async def _async_translate_single_node(
        self,
        node: TextNode,
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, int, int]:
        """Translate a single node. Returns (failed, in_tok, out_tok)."""
        if node.translated:
            return 0, 0, 0

        total_in, total_out = 0, 0
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp_text, in_tok, out_tok = await self._call_gemini(node.text, semaphore)
                total_in += in_tok
                total_out += out_tok

                resp_text = _clean_markdown_fences(resp_text)
                resp_text = _strip_conversational_prefix(resp_text)

                if _validate_translation(node.text, resp_text):
                    node.translated = resp_text
                    return 0, total_in, total_out

                # Validation failed
                if attempt < _MAX_RETRIES:
                    await _backoff_sleep(attempt)
                    continue
                node.translated = node.text
                return 1, total_in, total_out

            except Exception as e:
                logger.error(f"Single node failed (attempt {attempt}/{_MAX_RETRIES}): {e}")
                if attempt < _MAX_RETRIES:
                    await _backoff_sleep(attempt)
                    continue
                node.translated = node.text
                return 1, total_in, total_out

        node.translated = node.text
        return 1, total_in, total_out

    async def _async_translate_nodes_individually(
        self,
        nodes: List[TextNode],
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, int, int]:
        """Concurrent per-node fallback."""
        results = await asyncio.gather(
            *[self._async_translate_single_node(n, semaphore) for n in nodes],
            return_exceptions=False,
        )
        return (
            sum(r[0] for r in results),
            sum(r[1] for r in results),
            sum(r[2] for r in results),
        )

    # ── Orchestrator ──────────────────────────────────────────────────────────

    async def _translate_all_batches_async(
        self,
        nodes: List[TextNode],
        max_chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        file_name: str = "file.tex",
    ) -> int:
        chunks = split_into_paragraphs(nodes, max_chars=max_chunk_chars)
        total_batches = len(chunks)
        logger.info(
            f"Translating {len(nodes)} nodes in {total_batches} batches "
            f"(chunk={max_chunk_chars}, concurrency={_MAX_BATCH_CONCURRENCY})"
        )

        counter: list[int] = [0]
        tok_in: list[int] = [0]
        tok_out: list[int] = [0]
        lock = asyncio.Lock()
        done_event = asyncio.Event()

        async def _tracked_chunk(chunk: list) -> int:
            failed, in_t, out_t = await self._async_translate_chunk(chunk, semaphore)
            async with lock:
                counter[0] += 1
                tok_in[0] += in_t
                tok_out[0] += out_t
                done = counter[0]
                cum_in = tok_in[0]
                cum_out = tok_out[0]
            print(
                f"PROGRESS:BATCH_PROGRESS:{done}:{total_batches}:{file_name}",
                flush=True,
            )
            # Always emit a heartbeat with token info on batch completion
            print(
                f"PROGRESS:HEARTBEAT:✅ {file_name} batch {done}/{total_batches} | "
                f"In {in_t:,}/Out {out_t:,} | "
                f"Total In {cum_in:,}/Out {cum_out:,}",
                flush=True,
            )
            return failed

        async def _heartbeat() -> None:
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(done_event.wait()), timeout=5.0)
                except asyncio.TimeoutError:
                    if not done_event.is_set():
                        async with lock:
                            ci, co, d = tok_in[0], tok_out[0], counter[0]
                        if d > 0 and (ci > 0 or co > 0):
                            print(
                                f"PROGRESS:HEARTBEAT:Translating {file_name}... "
                                f"{d}/{total_batches} batches | "
                                f"In {ci:,}/Out {co:,} tokens",
                                flush=True,
                            )
                        else:
                            print(
                                f"PROGRESS:HEARTBEAT:Translating {file_name}... "
                                f"(waiting for API responses)",
                                flush=True,
                            )

        semaphore = asyncio.Semaphore(_MAX_BATCH_CONCURRENCY)
        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            results = await asyncio.gather(
                *[_tracked_chunk(chunk) for chunk in chunks],
                return_exceptions=False,
            )
        finally:
            done_event.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        total_in, total_out = tok_in[0], tok_out[0]
        print(
            f"PROGRESS:TOKENS_TOTAL:{total_in}:{total_out}:{file_name}",
            flush=True,
        )
        logger.info(f"[{file_name}] Gemini tokens — In: {total_in:,} | Out: {total_out:,}")
        return sum(results)

    # ── Public API ───────────────────────────────────────────────────────────

    def translate_text_nodes(
        self,
        nodes: List[TextNode],
        max_chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        file_name: str = "file.tex",
    ) -> tuple[list[TextNode], int]:
        if not nodes:
            return nodes, 0
        total_failed = asyncio.run(
            self._translate_all_batches_async(nodes, max_chunk_chars, file_name)
        )
        return nodes, total_failed

    # ── Legacy API ──────────────────────────────────────────────────────────

    def translate_latex(self, latex_content: str) -> str:
        return self._translate_latex_chunked(latex_content)

    def _translate_latex_chunked(self, content: str, chunk_size: int = 150) -> str:
        lines = content.split('\n')
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_size = 0
        for line in lines:
            current_chunk.append(line)
            current_size += 1
            is_empty = (line.strip() == "")
            if (current_size >= chunk_size and is_empty) or (current_size >= chunk_size * 2):
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        translated_chunks: list[str] = []
        logger.info(f"[Legacy] Translating {len(chunks)} chunks sequentially")
        for i, chunk in enumerate(chunks):
            try:
                response = self._sync_client.models.generate_content(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.translation_prompt,
                        temperature=0.1,
                    ),
                    contents=[chunk]
                )
                full_text = response.text or ""
                full_text = _clean_markdown_fences(full_text)
                full_text = _strip_conversational_prefix(full_text)
                translated_chunks.append(full_text if full_text else chunk)
            except Exception as e:
                logger.error(f"Legacy chunk {i+1} failed: {e}")
                translated_chunks.append(chunk)
        return '\n'.join(translated_chunks)
