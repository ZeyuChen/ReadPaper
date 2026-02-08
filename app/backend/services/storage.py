
import os
import shutil
import asyncio
from abc import ABC, abstractmethod
from typing import List
from google.cloud import storage
from ..logging_config import setup_logger

logger = setup_logger("StorageService")

class StorageService(ABC):
    @abstractmethod
    def list_files(self, prefix: str = "") -> List[str]:
        pass

    @abstractmethod
    async def upload_file(self, local_path: str, destination_path: str):
        pass

    @abstractmethod
    async def delete_file(self, path: str):
        pass

    @abstractmethod
    async def delete_folder(self, folder_path: str):
        pass
        
    @abstractmethod
    def get_user_storage(self, user_id: str) -> 'StorageService':
        """Returns a StorageService scoped to the user."""
        pass

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """Reads a text file content."""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str):
        """Writes text content to a file."""
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass

class LocalStorageService(StorageService):
    def __init__(self, base_path: str):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def _get_full_path(self, path: str) -> str:
        # Prevent path traversal
        full_path = os.path.abspath(os.path.join(self.base_path, path))
        if not full_path.startswith(self.base_path):
            raise ValueError(f"Invalid path: {path}")
        return full_path

    def list_files(self, prefix: str = "") -> List[str]:
        target_dir = self._get_full_path(prefix)
        if not os.path.exists(target_dir):
            return []
        # Return relative paths
        files = []
        for root, _, filenames in os.walk(target_dir):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.base_path)
                files.append(rel_path)
        return files

    async def upload_file(self, local_path: str, destination_path: str):
        dest_full = self._get_full_path(destination_path)
        os.makedirs(os.path.dirname(dest_full), exist_ok=True)
        await asyncio.to_thread(shutil.copy2, local_path, dest_full)

    async def delete_file(self, path: str):
        full = self._get_full_path(path)
        if os.path.exists(full):
             await asyncio.to_thread(os.remove, full)

    async def delete_folder(self, folder_path: str):
        full = self._get_full_path(folder_path)
        if os.path.exists(full):
             await asyncio.to_thread(shutil.rmtree, full)
             
    def get_user_storage(self, user_id: str) -> 'StorageService':
        # Return a new LocalStorageService rooted at base_path/users/{user_id}
        user_path = os.path.join(self.base_path, "users", user_id)
        return LocalStorageService(user_path)

    async def read_file(self, path: str) -> str:
        full = self._get_full_path(path)
        if not os.path.exists(full):
            raise FileNotFoundError(f"File not found: {path}")
        async with asyncio.Lock(): # Simple file lock not strictly needed for read but good practice
            with open(full, 'r', encoding='utf-8') as f:
                return await asyncio.to_thread(f.read)

    async def write_file(self, path: str, content: str):
        full = self._get_full_path(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        async with asyncio.Lock():
            with open(full, 'w', encoding='utf-8') as f:
                await asyncio.to_thread(f.write, content)

    async def exists(self, path: str) -> bool:
        full = self._get_full_path(path)
        return os.path.exists(full)

class GCSStorageService(StorageService):
    def __init__(self, bucket_name: str, root_prefix: str = ""):
        self.bucket_name = bucket_name
        self.root_prefix = root_prefix # e.g. "users/123/" or empty
        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name)
        except Exception as e:
            logger.error(f"GCS Init Error: {e}")
            raise

    def _get_gcs_path(self, path: str) -> str:
        # Join root_prefix and path
        if self.root_prefix:
            return f"{self.root_prefix.rstrip('/')}/{path.lstrip('/')}"
        return path

    def list_files(self, prefix: str = "") -> List[str]:
        full_prefix = self._get_gcs_path(prefix)
        blobs = self.client.list_blobs(self.bucket_name, prefix=full_prefix)
        results = []
        for blob in blobs:
            name = blob.name
            if self.root_prefix and name.startswith(self.root_prefix):
                name = name[len(self.root_prefix):].lstrip('/')
            results.append(name)
        return results

    async def upload_file(self, local_path: str, destination_path: str):
        full_dest = self._get_gcs_path(destination_path)
        blob = self.bucket.blob(full_dest)
        await asyncio.to_thread(blob.upload_from_filename, local_path)

    async def delete_file(self, path: str):
        full_path = self._get_gcs_path(path)
        blob = self.bucket.blob(full_path)
        if blob.exists():
            await asyncio.to_thread(blob.delete)

    async def delete_folder(self, folder_path: str):
        full_prefix = self._get_gcs_path(folder_path)
        if not full_prefix.endswith('/'):
            full_prefix += '/'
            
        blobs = list(self.client.list_blobs(self.bucket_name, prefix=full_prefix))
        
        def delete_blobs_batch():
            # GCS Batch delete is efficient
            # But client.delete_blobs(blobs) exists?
            # Yes, bucket.delete_blobs(blobs)
            if blobs:
                self.bucket.delete_blobs(blobs)

        await asyncio.to_thread(delete_blobs_batch)

    def get_user_storage(self, user_id: str) -> 'StorageService':
        # Return a new GCS service with a prefixed root
        new_prefix = f"users/{user_id}/"
        if self.root_prefix:
            new_prefix = f"{self.root_prefix.rstrip('/')}/users/{user_id}/"
        return GCSStorageService(self.bucket_name, root_prefix=new_prefix)

    async def read_file(self, path: str) -> str:
        full_path = self._get_gcs_path(path)
        blob = self.bucket.blob(full_path)
        if not blob.exists():
             raise FileNotFoundError(f"File not found: {path}")
        return await asyncio.to_thread(blob.download_as_text)

    async def write_file(self, path: str, content: str):
        full_path = self._get_gcs_path(path)
        blob = self.bucket.blob(full_path)
        await asyncio.to_thread(blob.upload_from_string, content)

    async def exists(self, path: str) -> bool:
        full_path = self._get_gcs_path(path)
        blob = self.bucket.blob(full_path)
        return await asyncio.to_thread(blob.exists)
