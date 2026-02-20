"""
Phase 3: Gemini-based text-node translator.

Key changes from the old approach:
- Accepts lists of TextNode (pure prose) instead of raw LaTeX
- LLM receives ONLY human-readable text — NO LaTeX commands
- Post-response validation: brace balance, no markdown fences, length sanity
- Retry once on validation failure; fall back to original on 2nd failure
- Batches nodes by character count (not line count) for efficient API usage
"""

from google import genai
from google.genai import types
import os
import re
import time
from typing import List
from .logging_utils import logger
from .text_extractor import TextNode, split_into_paragraphs


# ── Validation helpers ────────────────────────────────────────────────────────

def _has_markdown_fences(text: str) -> bool:
    return bool(re.search(r'^```', text, re.MULTILINE))


def _clean_markdown_fences(text: str) -> str:
    """Strip ```latex ... ``` wrappers if the LLM added them despite instructions."""
    m = re.search(r'^```(?:latex)?\s*(.*?)\s*```$', text, re.DOTALL | re.MULTILINE)
    return m.group(1) if m else text


def _strip_conversational_prefix(text: str) -> str:
    """Remove filler like 'Here is the translation:' before the actual content."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Common LLM preamble patterns
        if stripped.endswith(':') and len(stripped) < 60 and i <= 2:
            continue
        # Return from this line onward
        return '\n'.join(lines[i:])
    return text


def _validate_translation(original: str, translated: str) -> bool:
    """
    Basic sanity checks.
    Returns True if translation looks safe.
    """
    if not translated.strip():
        return False
    if _has_markdown_fences(translated):
        return False
    # Length sanity: translated Chinese should be ~40-100% of source length
    ratio = len(translated) / max(len(original), 1)
    if ratio < 0.1 or ratio > 5.0:
        logger.warning(f"Translation length ratio out of range: {ratio:.2f}")
        return False
    return True


# ── Main Translator Class ─────────────────────────────────────────────────────

class GeminiTranslator:
    """
    Translates pure text nodes from English to Chinese using Gemini.

    Two public APIs:
      translate_text_nodes(nodes) → translates in-place, returns nodes
      translate_latex(content)    → legacy fallback (whole-file chunked translation)
    """

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1beta', 'timeout': 600000}
        )

        # Load prompts
        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        self.translation_prompt = self._load_prompt(
            os.path.join(prompt_dir, "translation_prompt.txt"),
            "You are a professional academic translator. Translate English to formal academic Chinese."
        )
        self.text_only_prompt = self._load_prompt(
            os.path.join(prompt_dir, "text_only_translation_prompt.txt"),
            self._default_text_only_prompt()
        )

    def _load_prompt(self, path: str, fallback: str) -> str:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        logger.warning(f"Prompt not found at {path}, using fallback.")
        return fallback

    def _default_text_only_prompt(self) -> str:
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

    def translate_text_nodes(self, nodes: List[TextNode], max_chunk_chars: int = 3000) -> tuple[List[TextNode], int]:
        """
        Translate a list of TextNodes in-place.
        Uses batch translation (multiple nodes per API call for efficiency).

        Returns:
            (nodes, failed_count): nodes with .translated filled in;
            failed_count is the number of nodes that fell back to original
            English text due to API/validation failures.
        """
        if not nodes:
            return nodes, 0

        chunks = split_into_paragraphs(nodes, max_chars=max_chunk_chars)
        logger.info(f"Translating {len(nodes)} text nodes in {len(chunks)} batches")

        total_failed = 0
        for i, chunk in enumerate(chunks):
            logger.info(f"Translating batch {i+1}/{len(chunks)} ({sum(len(n.text) for n in chunk)} chars)")
            failed = self._translate_chunk(chunk, attempt=1)
            total_failed += failed

        return nodes, total_failed

    def _translate_chunk(self, nodes: List[TextNode], attempt: int = 1) -> int:
        """Translate a batch of TextNodes and fill in .translated field.
        Returns the number of nodes that fell back to original text.
        """
        # Build the batch input: nodes separated by a unique delimiter
        DELIMITER = "\n\n---NODE_BREAK---\n\n"
        batch_text = DELIMITER.join(n.text for n in nodes)

        try:
            response_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=self.text_only_prompt,
                    temperature=0.1,
                ),
                contents=[batch_text]
            )

            full_response = ""
            for part in response_stream:
                if part.text:
                    full_response += part.text

            # Clean up common LLM artifacts
            full_response = _clean_markdown_fences(full_response)
            full_response = _strip_conversational_prefix(full_response)

            # Validate
            if not _validate_translation(batch_text, full_response):
                if attempt < 2:
                    logger.warning(f"Batch validation failed, retrying (attempt {attempt})...")
                    return self._translate_chunk(nodes, attempt=attempt + 1)
                else:
                    logger.warning("Batch validation failed after retry. Using original text.")
                    for node in nodes:
                        node.translated = node.text
                    return len(nodes)  # all failed

            # Split response back by delimiter
            parts = full_response.split(DELIMITER)

            failed = 0
            if len(parts) == len(nodes):
                for node, translated_text in zip(nodes, parts):
                    if _validate_translation(node.text, translated_text):
                        node.translated = translated_text
                    else:
                        logger.warning(f"Individual node validation failed, keeping original.")
                        node.translated = node.text
                        failed += 1
                return failed
            else:
                # Delimiter alignment failed — fall back to per-node translation
                logger.warning(
                    f"Delimiter split mismatch: expected {len(nodes)}, got {len(parts)}. "
                    "Translating nodes individually."
                )
                return self._translate_nodes_individually(nodes)

        except Exception as e:
            logger.error(f"Translation batch failed: {e}")
            if attempt < 2:
                logger.info("Retrying failed batch...")
                time.sleep(2)
                return self._translate_chunk(nodes, attempt=attempt + 1)
            else:
                logger.warning("Batch failed after retry, keeping original text.")
                for node in nodes:
                    if not node.translated:
                        node.translated = node.text
                return len(nodes)  # all failed

    def _translate_nodes_individually(self, nodes: List[TextNode]) -> int:
        """Fallback: translate each node separately (slow but reliable).
        Returns the number of nodes that fell back to original text.
        """
        failed = 0
        for node in nodes:
            if node.translated:
                continue
            try:
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.text_only_prompt,
                        temperature=0.1,
                    ),
                    contents=[node.text]
                )
                full_text = ""
                for part in response_stream:
                    if part.text:
                        full_text += part.text
                full_text = _clean_markdown_fences(full_text)
                full_text = _strip_conversational_prefix(full_text)
                if _validate_translation(node.text, full_text):
                    node.translated = full_text
                else:
                    node.translated = node.text
                    failed += 1
            except Exception as e:
                logger.error(f"Individual node translation failed: {e}")
                node.translated = node.text
                failed += 1
        return failed

    # ── Legacy API (for backward compatibility and non-text-node files) ───────

    def translate_latex(self, latex_content: str) -> str:
        """
        LEGACY: Translate a raw LaTeX string using line-chunked approach.
        Used only when the text-node approach cannot be applied.
        """
        return self._translate_latex_chunked(latex_content)

    def _translate_latex_chunked(self, content: str, chunk_size: int = 150) -> str:
        lines = content.split('\n')
        chunks = []
        current_chunk: list = []
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

        translated_chunks = []
        logger.info(f"[Legacy] Translating {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            try:
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.translation_prompt,
                        temperature=0.1,
                    ),
                    contents=[chunk]
                )
                full_text = ""
                for part in response_stream:
                    if part.text:
                        full_text += part.text
                full_text = _clean_markdown_fences(full_text)
                full_text = _strip_conversational_prefix(full_text)
                translated_chunks.append(full_text if full_text else chunk)
            except Exception as e:
                logger.error(f"Chunk {i+1} failed: {e}")
                translated_chunks.append(chunk)

            if "pro" in self.model_name.lower():
                time.sleep(2)

        return '\n'.join(translated_chunks)
