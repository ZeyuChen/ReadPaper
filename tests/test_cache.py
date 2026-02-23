"""
Tests for translation cache service.
"""

import pytest
import json
import os
import asyncio
from app.backend.services.cache import TranslationCache
from app.backend.services.storage import LocalStorageService


@pytest.fixture
def cache_service(tmp_path):
    """Create a TranslationCache backed by a temporary local storage."""
    storage = LocalStorageService(str(tmp_path))
    return TranslationCache(storage)


@pytest.fixture
def event_loop():
    """Ensure each test gets a fresh event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def run(coro, loop=None):
    """Helper to run async functions in tests."""
    if loop is None:
        loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        if loop is not None:
            pass  # Don't close if passed in


# ── Cache miss ────────────────────────────────────────────────────────────────

def test_cache_miss_returns_none(cache_service):
    result = asyncio.get_event_loop().run_until_complete(
        cache_service.get_cached("2406.12345v1", "main.tex")
    ) if asyncio.get_event_loop().is_running() else asyncio.run(
        cache_service.get_cached("2406.12345v1", "main.tex")
    )
    assert result is None


def test_cache_miss_returns_none_simple(cache_service):
    result = asyncio.run(cache_service.get_cached("2406.12345v1", "main.tex"))
    assert result is None


# ── Cache put + get ───────────────────────────────────────────────────────────

def test_cache_put_and_get(cache_service):
    content = r"\documentclass{article}\begin{document}你好\end{document}"

    async def _test():
        await cache_service.put_cache("2406.12345v1", "main.tex", content, is_valid=True, model="flash")
        result = await cache_service.get_cached("2406.12345v1", "main.tex")
        assert result == content

    asyncio.run(_test())


# ── Invalid translations are NOT cached ───────────────────────────────────────

def test_invalid_translation_not_cached(cache_service):
    content = "partial content"

    async def _test():
        await cache_service.put_cache("2406.12345v1", "main.tex", content, is_valid=False)
        result = await cache_service.get_cached("2406.12345v1", "main.tex")
        assert result is None  # Should not be cached

    asyncio.run(_test())


# ── Version isolation ─────────────────────────────────────────────────────────

def test_version_isolation(cache_service):
    content_v1 = r"\begin{document}Version 1 translation\end{document}"
    content_v2 = r"\begin{document}Version 2 translation\end{document}"

    async def _test():
        # Cache v1
        await cache_service.put_cache("2406.12345v1", "main.tex", content_v1, is_valid=True)
        # Cache v2
        await cache_service.put_cache("2406.12345v2", "main.tex", content_v2, is_valid=True)

        # Retrieve separately
        result_v1 = await cache_service.get_cached("2406.12345v1", "main.tex")
        result_v2 = await cache_service.get_cached("2406.12345v2", "main.tex")

        assert result_v1 == content_v1
        assert result_v2 == content_v2
        assert result_v1 != result_v2  # Different versions, different content

    asyncio.run(_test())


# ── Complete marking ──────────────────────────────────────────────────────────

def test_mark_complete(cache_service):
    async def _test():
        # Initially not complete
        assert not await cache_service.is_complete("2406.12345v1")

        # Put a file and mark complete
        await cache_service.put_cache("2406.12345v1", "main.tex", "content", is_valid=True)
        await cache_service.mark_complete("2406.12345v1")

        assert await cache_service.is_complete("2406.12345v1")

    asyncio.run(_test())
