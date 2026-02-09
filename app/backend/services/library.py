
import json
import asyncio
from typing import List, Dict, Optional
from ..logging_config import setup_logger

logger = setup_logger("LibraryManager")
from .storage import StorageService

class LibraryManager:
    """
    Manages the user's personal library of papers.
    
    Persistence Strategy:
    Currently uses a simple `library.json` file stored in the user's storage root.
    
    Concurrency Note:
    This implementation is NOT thread-safe for concurrent writes from multiple processes
    (though safe enough for single-user async loop if not scaling horizontally).
    For production scaling, this should be replaced by a proper database (PostgreSQL/Firestore).
    """
    def __init__(self, storage: StorageService):
        self.storage = storage
        self.library_file = "library.json" # Relative to storage root
        self._cache: Dict[str, dict] = {} # In-memory cache
        self._loaded = False

    async def _load_library(self):
        """Loads library from storage if not already loaded."""
        if self._loaded:
            return

        try:
            if await self.storage.exists(self.library_file):
                content = await self.storage.read_file(self.library_file)
                self._cache = json.loads(content)
            else:
                self._cache = {}
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load library: {e}")
            self._cache = {}

    async def _save_library(self):
        """Saves current cache to storage."""
        try:
            content = json.dumps(self._cache, indent=2, ensure_ascii=False)
            await self.storage.write_file(self.library_file, content)
        except Exception as e:
            logger.error(f"Failed to save library: {e}")

    async def add_paper(self, arxiv_id: str, model: str, title: str, abstract: str, authors: List[str], categories: List[str]):
        """
        Adds or updates a paper in the library.
        If the paper exists, it updates the version info for the given model.
        """
        await self._load_library()
        
        if arxiv_id not in self._cache:
            self._cache[arxiv_id] = {
                "id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "versions": []
            }
        
        # Check if version exists
        versions = self._cache[arxiv_id]["versions"]
        existing = next((v for v in versions if v["model"] == model), None)
        
        if existing:
            existing["status"] = "completed"
            existing["timestamp"] = "now" # TODO: Real timestamp
        else:
            versions.append({
                "model": model,
                "status": "completed",
                "timestamp": "now"
            })
            
        await self._save_library()

    async def list_papers(self) -> List[dict]:
        await self._load_library()
        # Convert dict to list
        papers = list(self._cache.values())
        return papers

    async def get_paper(self, arxiv_id: str) -> Optional[dict]:
        await self._load_library()
        return self._cache.get(arxiv_id)

    async def delete_paper(self, arxiv_id: str) -> bool:
        await self._load_library()
        if arxiv_id in self._cache:
            del self._cache[arxiv_id]
            await self._save_library()
            return True
        return False
