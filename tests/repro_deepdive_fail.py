
import asyncio
import os
import shutil
import logging
from app.backend.services.storage import LocalStorageService
from app.backend.services.library import LibraryManager
from app.backend.main import run_translation_stream

# Setup basic logging
logging.basicConfig(level=logging.INFO)

async def repro():
    # Mock services
    storage = LocalStorageService("/tmp/repro_storage")
    lib = LibraryManager(storage)
    
    # User ID and Arxiv ID
    user_id = "debug_user"
    arxiv_id = "2505.09388"
    url = f"https://arxiv.org/abs/{arxiv_id}"
    
    # We need to monkeypatch main.py cleanup or just run it and hope it fails and we catch it before cleanup?
    # Actually main.py cleanup is in finally block.
    # So we should modify main.py to disable cleanup temporarily for debugging?
    # Or just use the CLI directly which might not cleanup?
    # The CLI `app.backend.arxiv_translator.main` cleans up?
    # Let's check `app/backend/arxiv_translator/main.py`.
    
    # CLI main.py DOES NOT cleanup work dir unless specified?
    # app/backend/main.py cleans up `work_root`.
    
    # So running the CLI directly is the best way to reproduce and keep files.
    
    cmd = [
        "python3", "-m", "app.backend.arxiv_translator.main",
        url,
        "--model", "flash",
        "--deepdive"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    # We need to set env vars
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath(".")
    env["MAX_CONCURRENT_REQUESTS"] = "8"
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await proc.communicate()
    
    print("STDOUT:", stdout.decode())
    print("STDERR:", stderr.decode())
    
    if proc.returncode != 0:
        print("Detailed error analysis needed.")

if __name__ == "__main__":
    asyncio.run(repro())
