import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
from ..logging_config import setup_logger

logger = setup_logger("library_manager")

class LibraryManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load library data: {e}")
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"Library saved to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save library data: {e}")

    async def add_paper(self, arxiv_id: str, model: str, title: str = "", abstract: str = "", authors: list = [], categories: list = []):
        # Reload to ensure consistency with disk
        await asyncio.to_thread(self._load)
        
        if arxiv_id not in self.data:
            self.data[arxiv_id] = {
                "id": arxiv_id,
                "added_at": datetime.now().isoformat(),
                "versions": [],
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories
            }
        else:
             # Update metadata if missing or new
             if title: self.data[arxiv_id]["title"] = title
             if abstract: self.data[arxiv_id]["abstract"] = abstract
             if authors: self.data[arxiv_id]["authors"] = authors
             if categories: self.data[arxiv_id]["categories"] = categories
        
        # Update version info
        version_entry = {
            "model": model,
            "translated_at": datetime.now().isoformat(),
            "status": "completed"
        }
        
        # Check if version exists
        exists = False
        for v in self.data[arxiv_id]["versions"]:
            if v["model"] == model:
                v.update(version_entry)
                exists = True
                break
        if not exists:
            self.data[arxiv_id]["versions"].append(version_entry)
            
        await asyncio.to_thread(self._save)

    def get_paper(self, arxiv_id: str):
        self._load()
        return self.data.get(arxiv_id)

    def list_papers(self):
        self._load()
        # Return list sorted by added_at desc
        papers = list(self.data.values())
        papers.sort(key=lambda x: x["added_at"], reverse=True)
        return papers

    async def delete_paper(self, arxiv_id: str):
        """
        Removes paper from library.json.
        Returns True if removed, False if not found.
        """
        await asyncio.to_thread(self._load)
        if arxiv_id in self.data:
            del self.data[arxiv_id]
            await asyncio.to_thread(self._save)
            return True
        return False
