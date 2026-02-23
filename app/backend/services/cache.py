"""
Translation cache service.

Stores validated translations keyed by versioned arXiv ID (e.g. 2406.12345v2)
to avoid redundant Gemini API calls. Only complete, integrity-validated
translations are cached.

Storage layout:
  _cache/{arxiv_id_v}/{filename}     — translated .tex content
  _cache/{arxiv_id_v}/meta.json      — metadata + per-file validity flags
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

from ..logging_config import setup_logger
from .storage import StorageService

logger = setup_logger("TranslationCache")


class TranslationCache:
    """Cache for validated translation results, backed by StorageService."""

    def __init__(self, storage: StorageService):
        """
        Args:
            storage: A root-level StorageService (NOT user-scoped).
                     Cache is shared across all users since translations
                     are deterministic for the same paper version + model.
        """
        self.storage = storage

    def _cache_prefix(self, arxiv_id_v: str) -> str:
        """GCS/local path prefix for a given versioned arxiv ID."""
        # Sanitize: replace dots and slashes to be safe
        safe_id = arxiv_id_v.replace("/", "_")
        return f"_cache/{safe_id}"

    def _meta_path(self, arxiv_id_v: str) -> str:
        return f"{self._cache_prefix(arxiv_id_v)}/meta.json"

    def _file_path(self, arxiv_id_v: str, filename: str) -> str:
        return f"{self._cache_prefix(arxiv_id_v)}/{filename}"

    async def _read_meta(self, arxiv_id_v: str) -> dict:
        """Read cache metadata, returns empty dict if not found."""
        meta_path = self._meta_path(arxiv_id_v)
        try:
            if await self.storage.exists(meta_path):
                content = await self.storage.read_file(meta_path)
                return json.loads(content)
        except Exception as e:
            logger.warning(f"Cache meta read error for {arxiv_id_v}: {e}")
        return {}

    async def _write_meta(self, arxiv_id_v: str, meta: dict):
        """Write cache metadata."""
        meta_path = self._meta_path(arxiv_id_v)
        try:
            content = json.dumps(meta, indent=2, ensure_ascii=False)
            await self.storage.write_file(meta_path, content)
        except Exception as e:
            logger.warning(f"Cache meta write error for {arxiv_id_v}: {e}")

    async def get_cached(self, arxiv_id_v: str, filename: str) -> Optional[str]:
        """
        Retrieve a cached translation for a specific file.

        Returns:
            Translated content string if cached and valid, None otherwise.
        """
        # Check metadata first — only return if the file was marked valid
        meta = await self._read_meta(arxiv_id_v)
        files_meta = meta.get("files", {})
        file_info = files_meta.get(filename, {})

        if not file_info.get("valid", False):
            return None

        file_path = self._file_path(arxiv_id_v, filename)
        try:
            if await self.storage.exists(file_path):
                content = await self.storage.read_file(file_path)
                logger.info(f"Cache HIT: {arxiv_id_v}/{filename}")
                return content
        except Exception as e:
            logger.warning(f"Cache file read error: {arxiv_id_v}/{filename}: {e}")

        return None

    async def put_cache(
        self,
        arxiv_id_v: str,
        filename: str,
        content: str,
        is_valid: bool,
        model: str = "",
    ):
        """
        Store a translation result in cache.

        Only stores file content if is_valid=True. Always updates metadata.
        """
        if not is_valid:
            logger.info(
                f"Cache SKIP (invalid): {arxiv_id_v}/{filename} — not caching"
            )
            return

        # Write the translated content
        file_path = self._file_path(arxiv_id_v, filename)
        try:
            await self.storage.write_file(file_path, content)
        except Exception as e:
            logger.error(f"Cache write error: {arxiv_id_v}/{filename}: {e}")
            return

        # Update metadata
        meta = await self._read_meta(arxiv_id_v)
        if not meta:
            meta = {
                "arxiv_id": arxiv_id_v,
                "model": model,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {},
                "complete": False,
            }

        meta.setdefault("files", {})[filename] = {
            "valid": True,
            "hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

        await self._write_meta(arxiv_id_v, meta)
        logger.info(f"Cache PUT: {arxiv_id_v}/{filename} (valid={is_valid})")

    async def is_complete(self, arxiv_id_v: str) -> bool:
        """Check if all files for this paper have been cached."""
        meta = await self._read_meta(arxiv_id_v)
        return meta.get("complete", False)

    async def mark_complete(self, arxiv_id_v: str):
        """Mark the entire paper translation as complete in cache."""
        meta = await self._read_meta(arxiv_id_v)
        if meta:
            meta["complete"] = True
            meta["completed_at"] = datetime.now(timezone.utc).isoformat()
            await self._write_meta(arxiv_id_v, meta)
            logger.info(f"Cache COMPLETE: {arxiv_id_v}")
