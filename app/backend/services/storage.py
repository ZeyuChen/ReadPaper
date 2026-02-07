import os
import shutil
import asyncio
from abc import ABC, abstractmethod
from ..logging_config import setup_logger

logger = setup_logger("storage_service")

class StorageService(ABC):
    @abstractmethod
    async def save_file(self, file_path: str, content: bytes) -> str:
        pass

    @abstractmethod
    async def delete_folder(self, folder_path: str):
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass

    async def upload_file(self, local_path: str, dest_path: str):
        pass

class LocalStorageService(StorageService):
    def __init__(self, base_path: str):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"LocalStorage initialized at {base_path}")

    def _get_abs_path(self, path: str) -> str:
        # If path is already absolute and starts with base_path, return it
        if os.path.isabs(path) and path.startswith(self.base_path):
            return path
        # Otherwise join with base_path
        return os.path.join(self.base_path, path)

    async def save_file(self, file_path: str, content: bytes) -> str:
        abs_path = self._get_abs_path(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        async with asyncio.to_thread(open, abs_path, "wb") as f:
             # Actually to_thread needs a function
             def write():
                 with open(abs_path, "wb") as f:
                     f.write(content)
             await asyncio.to_thread(write)
        logger.debug(f"Saved file to local storage: {abs_path}")
        return abs_path

    async def delete_folder(self, folder_path: str):
        abs_path = self._get_abs_path(folder_path)
        if os.path.exists(abs_path):
            await asyncio.to_thread(shutil.rmtree, abs_path)
            logger.info(f"Deleted local folder: {abs_path}")

    async def exists(self, path: str) -> bool:
        abs_path = self._get_abs_path(path)
        return os.path.exists(abs_path)
    
    async def upload_file(self, local_path: str, dest_path: str):
        # For local storage, if dest_path is relative, it might be same as local_path if we are working in place.
        # But if we treat it as "store to storage", we copy.
        abs_dest = self._get_abs_path(dest_path)
        if os.path.abspath(local_path) != os.path.abspath(abs_dest):
             os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
             await asyncio.to_thread(shutil.copy2, local_path, abs_dest)
             logger.debug(f"Uploaded (copied) file to local storage: {abs_dest}")

class GCSStorageService(StorageService):
    def __init__(self, bucket_name: str):
        from google.cloud import storage
        self.bucket_name = bucket_name
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        logger.info(f"GCSStorageService initialized for bucket: {bucket_name}")

    async def save_file(self, file_path: str, content: bytes) -> str:
        # Logic to upload bytes
        blob = self.bucket.blob(file_path)
        await asyncio.to_thread(blob.upload_from_string, content)
        logger.info(f"Uploaded bytes to GCS: gs://{self.bucket_name}/{file_path}")
        return f"gs://{self.bucket_name}/{file_path}"
    
    
    async def upload_file(self, local_path: str, dest_path: str):
        blob = self.bucket.blob(dest_path)
        await asyncio.to_thread(blob.upload_from_filename, local_path)

    async def delete_folder(self, folder_path: str):
        # List blobs with prefix and delete
        blobs = await asyncio.to_thread(list, self.client.list_blobs(self.bucket_name, prefix=folder_path))
        # Batch delete if possible, or loop
        for blob in blobs:
             await asyncio.to_thread(blob.delete)

    async def exists(self, path: str) -> bool:
        blob = self.bucket.blob(path)
        return await asyncio.to_thread(blob.exists)
