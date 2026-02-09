import os
import sys
import shutil
import asyncio
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, TypedDict, Optional, List

from .services.storage import LocalStorageService, GCSStorageService, StorageService
from .services.library import LibraryManager
from .services.auth import get_current_user
from .logging_config import setup_logger

logger = setup_logger("main_api")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Status structure
class TaskStatus(TypedDict):
    """
    Represents the status of a background translation task.
    
    Attributes:
        status: Current state ("queued", "processing", "completed", "failed").
        message: Human-readable status message (e.g., "Translating abstract.tex...").
        progress_percent: Integer percentage (0-100).
        details: Optional detailed error message or context.
    """
    status: str 
    message: str 
    progress_percent: int
    details: str

# Global Task Status (In-memory, simpler than DB for now, but not persistent across restarts)
# Key: arxiv_id (Global? No, should be user-specific to avoid collisions?)
# actually, task status is ephemeral. We can key by specific task ID or just arxiv_id if we assume one task per paper per user.
# Let's verify isolation: If User A translates X, and User B translates X.
# If we key by X, they collide.
# We should key by `user_id:arxiv_id`.
TASK_STATUS: Dict[str, TaskStatus] = {}

# Storage paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR)) # ReadPaper/

# Detect Cloud Run Environment
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None or os.getenv("CLOUD_RUN_ENV") == "true"

if IS_CLOUD_RUN:
    # In Cloud Run, only /tmp is writable for local cache
    PAPER_STORAGE_ROOT = "/tmp/paper_storage"
    logger.info("Running in Cloud Run environment. Using /tmp/paper_storage.")
else:
    PAPER_STORAGE_ROOT = os.path.join(PROJECT_ROOT, "paper_storage")

# Services Setup (Global Providers)
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local").lower() # 'local' or 'gcs'
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

# Root Storage Service (Factory Base)
if STORAGE_TYPE == "gcs" and GCS_BUCKET_NAME:
    try:
        logger.info(f"Initializing GCS Storage Root (Bucket: {GCS_BUCKET_NAME})...")
        root_storage = GCSStorageService(GCS_BUCKET_NAME)
        logger.info("GCS Storage Service initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize GCS: {e}")
        logger.warning("Falling back to Local Storage.")
        root_storage = LocalStorageService(PAPER_STORAGE_ROOT)
else:
    logger.info("Using Local Storage Service.")
    root_storage = LocalStorageService(PAPER_STORAGE_ROOT)

# Dependency Injection for Per-Request Services

def get_storage_service(user_id: str = Depends(get_current_user)) -> StorageService:
    """Returns a StorageService scoped to the current user."""
    return root_storage.get_user_storage(user_id)

def get_library_manager(storage: StorageService = Depends(get_storage_service)) -> LibraryManager:
    """Returns a LibraryManager using the user-scoped storage."""
    return LibraryManager(storage)

# Helper: Fetch Metadata
import feedparser
def fetch_arxiv_metadata(arxiv_id: str):
    try:
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        feed = feedparser.parse(url)
        if not feed.entries:
            return {}
        entry = feed.entries[0]
        return {
            "title": entry.title.replace("\n", " "),
            "abstract": entry.summary.replace("\n", " "),
            "authors": [author.name for author in entry.authors],
            "categories": [tag.term for tag in entry.tags]
        }
    except Exception as e:
        logger.error(f"Error fetching metadata: {e}")
        return {}

class TranslationRequest(BaseModel):
    arxiv_url: str
    model: str = "flash"
    deepdive: bool = False

def update_status(task_key: str, status: str, message: str = "", progress: int = 0, details: str = ""):
    logger.info(f"[{task_key}] {status}: {message} ({progress}%)")
    current = TASK_STATUS.get(task_key, {})
    # Preserve progress if not provided and status is processing
    if progress == 0 and status == "processing" and "progress_percent" in current:
        progress = current["progress_percent"]
        
    TASK_STATUS[task_key] = {
        "status": status, 
        "message": message,
        "progress_percent": progress,
        "details": details
    }

async def run_translation_stream(arxiv_url: str, model: str, arxiv_id: str, deepdive: bool, user_id: str, storage_service: StorageService, library_manager: LibraryManager):
    """
    Executes the translation pipeline in a background task.
    
    This function performs the following steps:
    1. Sets up a temporary local workspace.
    2. Downloads the original PDF from arXiv.
    3. Invokes the `arxiv-translator` module as a subprocess.
    4. Streams stdout/stderr from the subprocess to parse progress updates.
    5. Updates the global TASK_STATUS dictionary in real-time.
    6. Uploads the final translated PDF to the user's storage (Local or GCS).
    7. Updates the user's Library.
    
    Args:
        arxiv_url: The full URL of the arXiv paper.
        model: The Gemini model to use (e.g., 'flash', 'pro').
        arxiv_id: The extracted arXiv ID.
        deepdive: Whether to enable DeepDive analysis.
        user_id: The ID of the requesting user.
        storage_service: The user-scoped storage service.
        library_manager: The user-scoped library manager.
    """
    task_key = f"{user_id}:{arxiv_id}"
    try:
        # We need a local working directory for the subprocess (arxiv-translator works on local FS)
        # Even if using GCS, we download to local -> process -> upload.
        # Use /tmp/readpaper_work/{user_id}/{arxiv_id} to be safe/isolated locally
        
        # Base work dir (ephemeral)
        work_root = os.path.join(PAPER_STORAGE_ROOT, "work", user_id, arxiv_id)
        if os.path.exists(work_root):
            shutil.rmtree(work_root)
        os.makedirs(work_root, exist_ok=True)
        
        # 1. Download Original PDF
        update_status(task_key, "processing", "Downloading original PDF...", 5)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        original_pdf_name = f"{arxiv_id}.pdf"
        local_pdf_path = os.path.join(work_root, original_pdf_name)
        
        # Check User Storage first? (Maybe they deleted it locally but hav it in cloud?)
        # For RE-translation, we might check.
        # But simpler to just re-download from ArXiv for consistency.
        
        def download_pdf():
            return subprocess.run(
                ["curl", "-L", "-o", local_pdf_path, pdf_url], 
                capture_output=True, 
                text=True
            )
             
        proc = await asyncio.to_thread(download_pdf)
        if proc.returncode != 0:
             update_status(task_key, "processing", "Failed to download original PDF (Retrying...)", 5)
        
        # Upload Original to User Storage immediately
        if os.path.exists(local_pdf_path):
             await storage_service.upload_file(local_pdf_path, f"{arxiv_id}/{original_pdf_name}")

        # 2. Run arxiv-translator (Module call)
        # We need to run it in the work_root
        # arxiv-translator expects to work in CWD or create a workspace_{arxiv_id} there.
        # We will let it run in work_root.
        
        cmd = [
            sys.executable, "-m", "app.backend.arxiv_translator.main",
            arxiv_url,
            "--model", model
        ]
        
        if deepdive:
            cmd.append("--deepdive")
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["ARXIV_TRANSLATOR_LOG_DIR"] = os.path.abspath(os.path.join(BASE_DIR, "logs")) 
        project_root = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_root, # It will create workspace_{id} inside here
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
                # Stream logs
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8').strip()
            if line.startswith("PROGRESS:"):
                # Parse progress (simplified)
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    code, rest = parts[1], parts[2]
                    # Map codes to status
                    status_map = {
                        "TRANSLATING": (10, "Translating..."),
                        "COMPILING": (90, "Compiling PDF..."),
                        "COMPLETED": (100, "Done"),
                        "FAILED": (0, "Failed"),
                        "ANALYZING": (10, "Analyzing DeepDive...")
                    }
                    
                    # Fetch current progress to ensure monotonicity
                    current_status = TASK_STATUS.get(task_key, {})
                    current_pct = current_status.get("progress_percent", 0)

                    # Handle advanced TRANSLATING:X:Y:File
                    if code == "TRANSLATING" and ":" in rest:
                         try:
                             # Format: count:total:filename
                             # Use robust splitting
                             p_parts = rest.split(":", 2)
                             if len(p_parts) >= 3:
                                 c_part, t_part, msg = p_parts[0], p_parts[1], p_parts[2]
                                 count = int(c_part)
                                 total = int(t_part)
                                 
                                 pct = current_pct
                                 if total > 0:
                                     # Map 10% -> 90%
                                     # Formula: 10 + (count / total) * 80
                                     # When count=0, pct=10.
                                     pct = 10 + int((count / total) * 80)
                                 
                                 # Ensure monotonicity
                                 if pct < current_pct:
                                     pct = current_pct
                                     
                                 update_status(task_key, "processing", f"Translating: {msg}", pct)
                             else:
                                 update_status(task_key, "processing", f"Translating: {rest}")
                         except Exception as e:
                             # Fallback don't reset progress
                             update_status(task_key, "processing", f"Translating: {rest.split(':')[-1]}")

                    # Handle advanced ANALYZING:X:Y:File
                    elif code == "ANALYZING" and ":" in rest:
                         try:
                             # Format: count:total:filename
                             p_parts = rest.split(":", 2)
                             if len(p_parts) >= 3:
                                 c_part, t_part, msg = p_parts[0], p_parts[1], p_parts[2]
                                 count = int(c_part)
                                 total = int(t_part)
                                 
                                 pct = current_pct
                                 if total > 0:
                                     # Map 10% -> 40% (DeepDive phase)
                                     pct = 10 + int((count / total) * 30)
                                 
                                 # Ensure monotonicity
                                 if pct < current_pct:
                                     pct = current_pct

                                 update_status(task_key, "processing", f"DeepDive Analyzing: {msg}", pct)
                             else:
                                 update_status(task_key, "processing", f"DeepDive Analyzing: {rest}")
                         except:
                             update_status(task_key, "processing", f"DeepDive Analyzing: {rest.split(':')[-1]}")

                    elif code in status_map:
                         prog, msg = status_map[code]
                         if code == "COMPLETED":
                             update_status(task_key, "completed", rest, 100)
                         elif code == "FAILED":
                             update_status(task_key, "failed", rest, 0)
                         else:
                             # Generic status update (don't regress progress usually, unless starting phase)
                             if prog < current_pct and prog > 0:
                                 prog = current_pct
                             update_status(task_key, "processing", rest, prog, msg)
                    else:
                         update_status(task_key, "processing", rest)

        return_code = await process.wait()
        
        if return_code != 0:
            stderr = await process.stderr.read()
            err_msg = stderr.decode('utf-8')
            update_status(task_key, "failed", f"Process failed: {err_msg[:200]}")
            return

        # 3. Upload Results to User Storage
        # Expected outputs in work_root (CWD) or workspace directory
        workspace_dir = os.path.join(work_root, f"workspace_{arxiv_id}")
        
        # Find any PDF ending in _zh*.pdf in work_root (primary) or workspace_dir (fallback)
        found_pdf_path = None
        
        # Check work_root first
        for f in os.listdir(work_root):
             if f.endswith(".pdf") and "_zh" in f:
                 found_pdf_path = os.path.join(work_root, f)
                 break
        
        # Fallback to workspace dir
        if not found_pdf_path and os.path.exists(workspace_dir):
             for f in os.listdir(workspace_dir):
                 if f.endswith(".pdf") and "_zh" in f:
                     found_pdf_path = os.path.join(workspace_dir, f)
                     break
        
        if found_pdf_path:
             pdf_filename = os.path.basename(found_pdf_path)
             await storage_service.upload_file(found_pdf_path, f"{arxiv_id}/{pdf_filename}")
             
             # Update Library
             meta = fetch_arxiv_metadata(arxiv_id)
             await library_manager.add_paper(
                 arxiv_id, model, 
                 meta.get("title", arxiv_id), 
                 meta.get("abstract", ""), 
                 meta.get("authors", []), 
                 meta.get("categories", [])
             )
             update_status(task_key, "completed", "Processing complete.")
        else:
             update_status(task_key, "failed", "PDF not found after processing.")

    except Exception as e:
        logger.error(f"Task Exception: {e}")
        update_status(task_key, "failed", str(e))
    finally:
        # Cleanup ephemeral work dir
        if os.path.exists(work_root):
            try:
                shutil.rmtree(work_root)
            except:
                pass

async def run_translation_wrapper(arxiv_url: str, model: str, arxiv_id: str, deepdive: bool, user_id: str, storage: StorageService, lib: LibraryManager):
    await run_translation_stream(arxiv_url, model, arxiv_id, deepdive, user_id, storage, lib)

@app.get("/library")
async def get_library(library_manager: LibraryManager = Depends(get_library_manager)):
    # Returns papers for current user
    return await library_manager.list_papers()

@app.delete("/library/{arxiv_id}")
async def delete_paper(
    arxiv_id: str, 
    library_manager: LibraryManager = Depends(get_library_manager),
    storage_service: StorageService = Depends(get_storage_service)
):
    success = await library_manager.delete_paper(arxiv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    await storage_service.delete_folder(arxiv_id)
    return {"message": "Deleted"}

@app.post("/translate")
async def translate_paper(
    request: TranslationRequest, 
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
    storage_service: StorageService = Depends(get_storage_service),
    library_manager: LibraryManager = Depends(get_library_manager)
):
    parts = request.arxiv_url.split("/")
    arxiv_id = parts[-1].replace(".pdf", "")
    
    # Check Library
    paper = await library_manager.get_paper(arxiv_id)
    if paper:
        # Simplified check: if exists, return it
        return {"message": "Already completed", "arxiv_id": arxiv_id, "status": "completed"}
    
    task_key = f"{user_id}:{arxiv_id}"
    update_status(task_key, "queued", "Started")
    
    background_tasks.add_task(
        run_translation_wrapper, 
        request.arxiv_url, request.model, arxiv_id, request.deepdive,
        user_id, storage_service, library_manager
    )
    
    return {"message": "Started", "arxiv_id": arxiv_id}

@app.get("/status/{arxiv_id}")
async def get_status(
    arxiv_id: str, 
    user_id: str = Depends(get_current_user)
):
    task_key = f"{user_id}:{arxiv_id}"
    status = TASK_STATUS.get(task_key)
    if not status:
        return {"status": "not_found"}
    return status

@app.get("/paper/{arxiv_id}/{file_type}")
async def get_paper(
    arxiv_id: str, 
    file_type: str,
    storage_service: StorageService = Depends(get_storage_service)
):
    """
    Serves the PDF file (original or translated) for a specific paper.
    
    Current Implementation:
    - For LocalStorage: Serves the file directly from the filesystem using FileResponse.
    - For GCS: Generates a signed URL and redirects the client to it.
    
    Args:
        arxiv_id: The ID of the paper.
        file_type: "original" or "translated".
    """
    # Proxy file download from User Storage
    # List files to find match
    files = storage_service.list_files(f"{arxiv_id}/")
    target = None
    
    if file_type == "original":
        target = f"{arxiv_id}/{arxiv_id}.pdf"
    elif file_type == "translated":
        # Find *zh*.pdf
        for f in files:
            if "_zh" in f and f.endswith(".pdf"):
                target = f"{arxiv_id}/{os.path.basename(f)}" 
                break
    
    if not target:
        raise HTTPException(status_code=404, detail="File not found")

    if isinstance(storage_service, LocalStorageService):
        full_path = storage_service._get_full_path(target)
        return FileResponse(full_path)
    elif isinstance(storage_service, GCSStorageService):
        # Generate Signed URL for direct access (more efficient than proxying)
        blob = storage_service.bucket.blob(storage_service._get_gcs_path(target))
        # Note: This requires the service account to have Token Creator permissions
        if blob.exists():
            url = blob.generate_signed_url(version="v4", expiration=3600, method="GET")
            return RedirectResponse(url)
            
    raise HTTPException(status_code=404, detail="File could not be served")

@app.get("/tasks")
async def get_tasks(user_id: str = Depends(get_current_user)):
    """
    Returns the status of current background tasks for the user.
    """
    # Filter tasks by user_id prefix in key "user_id:arxiv_id"
    user_tasks = []
    prefix = f"{user_id}:"
    
    for key, status in TASK_STATUS.items():
        if key.startswith(prefix):
            arxiv_id = key.split(":", 1)[1]
            task_data = status.copy()
            task_data["arxiv_id"] = arxiv_id
            # Map "progress_percent" to "progress" for frontend compatibility
            task_data["progress"] = task_data.get("progress_percent", 0)
            user_tasks.append(task_data)
            
    return user_tasks
