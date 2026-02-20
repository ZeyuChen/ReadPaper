"""
Phase 3: Gemini-based text-node translator — Async Concurrent Edition.

Performance improvements over the previous version:
- All translation batches within a file fire CONCURRENTLY via asyncio.gather.
- Fallback per-node translation is also concurrent (asyncio.gather).
- Async Gemini client (genai.AsyncClient) replaces the blocking sync client.
- Chunk size increased 3 000 → 6 000 chars (fewer API round-trips per file).
- asyncio.Semaphore caps concurrency to respect API rate limits.

The public interface (translate_text_nodes) is call-compatible with the old
version.  ProcessPoolExecutor workers call asyncio.run(…) around it.
"""

from google import genai
from google.genai import types
import asyncio
import os
import re
import time
from typing import List
from .logging_utils import logger
from .text_extractor import TextNode, split_into_paragraphs


# ── Config ────────────────────────────────────────────────────────────────────

# Maximum concurrent Gemini API calls per worker process.
# Default 8: safe for Flash quota; raise if you have higher limits.
_MAX_BATCH_CONCURRENCY = int(os.getenv("MAX_BATCH_CONCURRENCY", "8"))

# Default max chars per translation batch.
_DEFAULT_CHUNK_CHARS = int(os.getenv("TRANSLATION_CHUNK_CHARS", "6000"))


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
        if stripped.endswith(':') and len(stripped) < 60 and i <= 2:
            continue
        return '\n'.join(lines[i:])
    return text


def _validate_translation(original: str, translated: str) -> bool:
    """
    Basic sanity checks — returns True if translation looks safe.
    Rules (immutable, don't mutate original or translated strings):
    - Must not be empty
    - Must not contain markdown fences
    - Length ratio 0.1–5.0 relative to source
    """
    if not translated.strip():
        return False
    if _has_markdown_fences(translated):
        return False
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
      translate_text_nodes(nodes)  → sync wrapper, runs asyncio event loop
      translate_latex(content)     → legacy fallback (whole-file chunked)

    All Gemini calls are non-blocking (async).  A Semaphore limits concurrent
    in-flight requests to MAX_BATCH_CONCURRENCY to avoid rate-limit errors.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model_name = model_name

        # Single client for both sync (legacy) and async (concurrent batches).
        # Async calls use the client.aio.models.* namespace — no separate AsyncClient needed.
        # Install google-genai[aiohttp] for best async performance:
        #   pip install 'google-genai[aiohttp]'
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={'api_version': 'v1beta', 'timeout': 600000}
        )

        # Convenience aliases
        self._sync_client = self._client  # used by legacy translate_latex

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

    # ── Internal helpers ──────────────────────────────────────────────────────

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

    # ── Async core ───────────────────────────────────────────────────────────

    async def _async_translate_chunk(
        self,
        nodes: List[TextNode],
        semaphore: asyncio.Semaphore,
        attempt: int = 1,
    ) -> int:
        """
        Async: translate a batch of TextNodes and fill in .translated.
        Acquires semaphore to cap concurrent in-flight requests.
        Returns the number of nodes that fell back to original text.
        """
        DELIMITER = "\n\n---NODE_BREAK---\n\n"
        batch_text = DELIMITER.join(n.text for n in nodes)

        async with semaphore:
            try:
                response_stream = await self._client.aio.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.text_only_prompt,
                        temperature=0.1,
                    ),
                    contents=[batch_text]
                )

                full_response = ""
                async for part in response_stream:
                    if part.text:
                        full_response += part.text

                full_response = _clean_markdown_fences(full_response)
                full_response = _strip_conversational_prefix(full_response)

                if not _validate_translation(batch_text, full_response):
                    if attempt < 2:
                        logger.warning("Batch validation failed, retrying async...")
                        return await self._async_translate_chunk(nodes, semaphore, attempt + 1)
                    logger.warning("Batch validation failed after retry. Using original.")
                    for node in nodes:
                        node.translated = node.text
                    return len(nodes)

                parts = full_response.split(DELIMITER)
                if len(parts) == len(nodes):
                    failed = 0
                    for node, translated_text in zip(nodes, parts):
                        if _validate_translation(node.text, translated_text):
                            node.translated = translated_text
                        else:
                            node.translated = node.text
                            failed += 1
                    return failed
                else:
                    # Delimiter alignment mismatch → concurrent per-node fallback
                    logger.warning(
                        f"Delimiter split mismatch: expected {len(nodes)}, got {len(parts)}. "
                        "Falling back to per-node concurrent translation."
                    )
                    return await self._async_translate_nodes_individually(nodes, semaphore)

            except Exception as e:
                logger.error(f"Async batch translation failed: {e}")
                if attempt < 2:
                    logger.info("Retrying failed async batch in 2 s...")
                    await asyncio.sleep(2)
                    return await self._async_translate_chunk(nodes, semaphore, attempt + 1)
                for node in nodes:
                    if not node.translated:
                        node.translated = node.text
                return len(nodes)

    async def _async_translate_single_node(
        self,
        node: TextNode,
        semaphore: asyncio.Semaphore,
    ) -> int:
        """Translate a single TextNode asynchronously. Returns 1 on failure, 0 on success."""
        if node.translated:
            return 0
        async with semaphore:
            try:
                response_stream = await self._client.aio.models.generate_content_stream(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=self.text_only_prompt,
                        temperature=0.1,
                    ),
                    contents=[node.text]
                )
                full_text = ""
                async for part in response_stream:
                    if part.text:
                        full_text += part.text
                full_text = _clean_markdown_fences(full_text)
                full_text = _strip_conversational_prefix(full_text)
                if _validate_translation(node.text, full_text):
                    node.translated = full_text
                    return 0
                node.translated = node.text
                return 1
            except Exception as e:
                logger.error(f"Single node async translation failed: {e}")
                node.translated = node.text
                return 1

    async def _async_translate_nodes_individually(
        self,
        nodes: List[TextNode],
        semaphore: asyncio.Semaphore,
    ) -> int:
        """Concurrent fallback: fire all individual-node calls simultaneously."""
        results = await asyncio.gather(
            *[self._async_translate_single_node(n, semaphore) for n in nodes],
            return_exceptions=False,
        )
        return sum(results)

    async def _translate_all_batches_async(
        self,
        nodes: List[TextNode],
        max_chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        file_name: str = "file.tex",
    ) -> int:
        """
        Split nodes into batches, then fire ALL batches concurrently.
        Emits PROGRESS:BATCH_PROGRESS IPC after each batch so the frontend
        progress bar advances smoothly instead of hanging then jumping.
        Also runs a heartbeat coroutine that emits PROGRESS:HEARTBEAT every 5 s.
        Returns total failed node count.
        """
        chunks = split_into_paragraphs(nodes, max_chars=max_chunk_chars)
        total_batches = len(chunks)
        logger.info(
            f"Translating {len(nodes)} nodes in {total_batches} concurrent batches "
            f"(chunk_chars={max_chunk_chars}, max_concurrency={_MAX_BATCH_CONCURRENCY})"
        )

        # Shared mutable counter tracked under a lock (immutability N/A for counters).
        counter: list[int] = [0]
        lock = asyncio.Lock()
        done_event = asyncio.Event()

        async def _tracked_chunk(chunk: list) -> int:
            """Wrapper: translate a chunk, then bump the IPC counter."""
            failed = await self._async_translate_chunk(chunk, semaphore)
            async with lock:
                counter[0] += 1
                done = counter[0]
            # Emit IPC on stdout — parsed by backend main.py run_translation_stream
            print(
                f"PROGRESS:BATCH_PROGRESS:{done}:{total_batches}:{file_name}",
                flush=True,
            )
            return failed

        async def _heartbeat() -> None:
            """Emit a heartbeat IPC every 5 s so the frontend never sees a dead process."""
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(done_event.wait()), timeout=5.0)
                except asyncio.TimeoutError:
                    if not done_event.is_set():
                        print("PROGRESS:HEARTBEAT:Translating...", flush=True)

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

        return sum(results)

    # ── Public API ───────────────────────────────────────────────────────────

    def translate_text_nodes(
        self,
        nodes: List[TextNode],
        max_chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        file_name: str = "file.tex",
    ) -> tuple[list[TextNode], int]:
        """
        Translate a list of TextNodes in-place.

        All batches are fired concurrently via asyncio.gather, limited by
        MAX_BATCH_CONCURRENCY (default 8).  Emits PROGRESS:BATCH_PROGRESS IPC
        after each completed batch so the backend can stream fine-grained
        progress to the frontend.

        Returns:
            (nodes, failed_count) — nodes with .translated filled in.
            failed_count: nodes that fell back to original English.
        """
        if not nodes:
            return nodes, 0

        total_failed = asyncio.run(
            self._translate_all_batches_async(nodes, max_chunk_chars, file_name)
        )
        return nodes, total_failed

    # ── Legacy API (backward compatibility) ──────────────────────────────────

    def translate_latex(self, latex_content: str) -> str:
        """
        LEGACY: Translate a raw LaTeX string using line-chunked approach.
        Used only when the text-node approach cannot be applied.
        """
        return self._translate_latex_chunked(latex_content)

    def _translate_latex_chunked(self, content: str, chunk_size: int = 150) -> str:
        """Sequential legacy fallback — uses sync client to avoid event-loop conflicts."""
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
                response_stream = self._sync_client.models.generate_content_stream(
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
                logger.error(f"Legacy chunk {i+1} failed: {e}")
                translated_chunks.append(chunk)

        return '\n'.join(translated_chunks)
