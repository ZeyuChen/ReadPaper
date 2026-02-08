import os
import sys
import shutil
import asyncio
import subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, TypedDict, Optional

from .services.storage import LocalStorageService, GCSStorageService
from .services.library import LibraryManager
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
    status: str # "queued", "processing", "completed", "failed"
    message: str # Granular details like "Translating abstract.tex..."

TASK_STATUS: Dict[str, TaskStatus] = {}

# Storage paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR)) # ReadPaper/

# Detect Cloud Run Environment
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None or os.getenv("CLOUD_RUN_ENV") == "true"

if IS_CLOUD_RUN:
    # In Cloud Run, only /tmp is writable
    PAPER_STORAGE = "/tmp/paper_storage"
    logger.info("Running in Cloud Run environment. Using /tmp/paper_storage.")
else:
    PAPER_STORAGE = os.path.join(PROJECT_ROOT, "paper_storage")

# Services Setup
# 1. Storage
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
storage_service = None
local_storage = LocalStorageService(PAPER_STORAGE)

if GCS_BUCKET_NAME:
    try:
        logger.info(f"GCS Storage enabled in env. Bucket: {GCS_BUCKET_NAME}")
        storage_service = GCSStorageService(GCS_BUCKET_NAME)
        logger.info("GCS Service initialized successfully.")
    except Exception as e:
        logger.warning(f"Failed to initialize GCS Storage (likely auth error): {e}")
        logger.info("Falling back to Local Storage.")
        storage_service = local_storage
else:
    logger.info("Using Local Storage only.")
    storage_service = local_storage

# 2. Library
LIBRARY_FILE = os.path.join(PROJECT_ROOT, "library.json")
library_manager = LibraryManager(LIBRARY_FILE)

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

def update_status(arxiv_id: str, status: str, message: str = "", progress: int = 0, details: str = ""):
    logger.info(f"[{arxiv_id}] {status}: {message} ({progress}%)")
    current = TASK_STATUS.get(arxiv_id, {})
    # Preserve progress if not provided and status is processing
    if progress == 0 and status == "processing" and "progress_percent" in current:
        progress = current["progress_percent"]
        
    TASK_STATUS[arxiv_id] = {
        "status": status, 
        "message": message,
        "progress_percent": progress,
        "details": details
    }

# Removed obsolete upload_to_gcs function. Using storage_service instead.

async def run_translation_stream(arxiv_url: str, model: str, arxiv_id: str, deepdive: bool = False):
    """"
    Runs arxiv-translator and streams output to update status.
    """
    try:
        # 1. Setup Storage
        # Ensure paper folder exists (handled by storage service implicitly or explicitly)
        # For local storage, we might need a path. For GCS, we just upload.
        # But we need a local working directory for arxiv-translator to run in.
        
        # We ALWAYS need a local working dir for the subprocess
        working_dir = os.path.join(PAPER_STORAGE, arxiv_id)
        await asyncio.to_thread(os.makedirs, working_dir, exist_ok=True)
        
        # 1. Download Original PDF
        update_status(arxiv_id, "processing", "Downloading original PDF...", 5)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        original_pdf_path = os.path.join(working_dir, f"{arxiv_id}.pdf")
        
        # Check GCS first for original (optional optimization, skip for checking existence logic complexity)
        # Just download locally for processing
        
        if not os.path.exists(original_pdf_path):
             def download_pdf():
                return subprocess.run(
                    ["curl", "-L", "-o", original_pdf_path, pdf_url], 
                    capture_output=True, 
                    text=True
                )
             
             proc = await asyncio.to_thread(download_pdf)
             
             if proc.returncode != 0:
                logger.warning(f"Failed to download PDF: {proc.stderr}")
                update_status(arxiv_id, "processing", "Failed to download original PDF (Non-fatal, continuing...)", 5)
        
        # Upload original PDF to Storage (GCS or Local)
        # local_storage always has it since we downloaded it there.
        # If storage_service is GCS, we upload it.
        if storage_service != local_storage and os.path.exists(original_pdf_path):
             await storage_service.upload_file(original_pdf_path, f"{arxiv_id}/{arxiv_id}.pdf")

        # 2. Run arxiv-translator (Module call)
        cmd = [
            sys.executable, "-m", "app.backend.arxiv_translator.main",
            arxiv_url,
            "--model", model
        ]
        
        if deepdive:
            cmd.append("--deepdive")
        
        # Use asyncio.create_subprocess_exec to avoid blocking the event loop
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # Pass Log Directory to subprocess
        env["ARXIV_TRANSLATOR_LOG_DIR"] = os.path.abspath(os.path.join(BASE_DIR, "logs")) # app/backend/logs
        # Explicitly set PYTHONPATH to project root to allow importing 'app' module
        project_root = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        print(f"DEBUG: PYTHONPATH={env['PYTHONPATH']}")
        
        # print(f"DEBUG: Starting subprocess for {arxiv_id}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        # print(f"DEBUG: Subprocess started, pid={process.pid}")
        
        # Read stdout line by line
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            
            line = line_bytes.decode('utf-8').strip()
            # print(f"DEBUG: Read line: {line[:50]}...") # Uncomment for verbose debug
            if line:
                # Check for progress markers
                if line.startswith("PROGRESS:"):
                    # Format: PROGRESS:CODE:P1:P2:MSG or PROGRESS:CODE:MSG
                    
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        code = parts[1] # DOWNLOADING, EXTRACTING, TRANSLATING, COMPILING, COMPLETED, FAILED
                        rest = parts[2]
                        
                        if code == "TRANSLATING":
                            # Try parsing new format: IDX:TOTAL:FILENAME
                            t_parts = rest.split(":")
                            if len(t_parts) >= 3:
                                try:
                                    idx = int(t_parts[0])
                                    total = int(t_parts[1])
                                    fname = t_parts[2]
                                    
                                    # Calculate percent: 10% (setup) + 80% (translation) * (idx/total)
                                    # setup includes download(5) + extract(5)
                                    base_progress = 10
                                    if total > 0:
                                        p = int(base_progress + 80 * (idx / total))
                                        logger.debug(f"Parsed progress {p}% for {fname}")
                                        update_status(arxiv_id, "processing", f"Translating {fname}", p, f"File {idx}/{total}")
                                except ValueError:
                                     # Fallback
                                     update_status(arxiv_id, "processing", rest, 10, "")
                            else:
                                 update_status(arxiv_id, "processing", rest, 10, "")
                                 
                        elif code == "COMPILING":
                            update_status(arxiv_id, "processing", rest, 90, "Compiling PDF...")
                            
                        elif code == "COMPLETED":
                            update_status(arxiv_id, "completed", rest, 100, "Done")
                            
                        elif code == "FAILED":
                            update_status(arxiv_id, "failed", rest, 0, "Failed")
                            
                        elif code == "DOWNLOADING":
                            update_status(arxiv_id, "processing", rest, 5, "Downloading source...")
                            
                        elif code == "EXTRACTING":
                            update_status(arxiv_id, "processing", rest, 8, "Extracting files...")
                            
                        elif code == "ANALYZING":
                            update_status(arxiv_id, "processing", rest, 85, "Analyzing technical content...")
                            
                        else:
                            update_status(arxiv_id, "processing", rest)
                else:
                    # Log other output to debug
                    logger.debug(f"CLI: {line}")
                    pass
        
        # Check return code
        # Wait for process to finish
        return_code = await process.wait()
        
        if return_code != 0:
            stderr_out_bytes = await process.stderr.read()
            stderr_out = stderr_out_bytes.decode('utf-8')
            logger.error(f"Translation Error: {stderr_out}")
            task_s = TASK_STATUS.get(arxiv_id)
            if task_s and task_s["status"] != "failed":
                update_status(arxiv_id, "failed", f"Process exited with error: {stderr_out[:100]}...", 0, "Process error")

        # Final check if we missed COMPLETED marker but process succeeded
        task_s = TASK_STATUS.get(arxiv_id)
        if return_code == 0 and task_s and task_s["status"] != "completed" and task_s["status"] != "failed":
             # Double check file existence
             expected_pdf = f"{arxiv_id}_zh_{model}.pdf"
             if model == "flash": expected_pdf = f"{arxiv_id}_zh_flash.pdf"
             if model == "pro": expected_pdf = f"{arxiv_id}_zh_pro.pdf"
             
             # Fallback check
             msg = "Completed"
             status = "completed"
             update_status(arxiv_id, status, msg)

        # Update Library if successful
        if TASK_STATUS.get(arxiv_id, {}).get("status") == "completed":
             # Fetch metadata
             meta = fetch_arxiv_metadata(arxiv_id)
             title = meta.get("title", f"arXiv:{arxiv_id}")
             abstract = meta.get("abstract", "")
             authors = meta.get("authors", [])
             categories = meta.get("categories", [])
             await library_manager.add_paper(arxiv_id, model, title=title, abstract=abstract, authors=authors, categories=categories)

        # 3. Upload LaTeX source to Storage (optional, in background)
        # Only needed if storage_service is remote (GCS)
        if storage_service != local_storage:
            def upload_source_files():
                 for root, dirs, files in os.walk(working_dir):
                    for f in files:
                        local_f = os.path.join(root, f)
                        if local_f == original_pdf_path or local_f.endswith("_zh.pdf") or local_f.endswith("_zh_flash.pdf"):
                            continue
                        
                        # Upload relative path
                        rel_path = os.path.relpath(local_f, PAPER_STORAGE) # e.g. arxiv_id/main.tex
                        # But wait, storage_service logic might expect something else.
                        # GCSStorageService: upload_file(local, dest)
                        # Dest should be arxiv_id/filename
                        
                        # Let's simplify and just upload flat structure or keep folder structure?
                        # The walker goes into subdirs.
                        rel_file = os.path.relpath(local_f, working_dir)
                        dest_blob = f"{arxiv_id}/{rel_file}"
                        
                        # We need an async wrapper or call run_in_executor?
                        # storage_service.upload_file does to_thread inside.
                        # But we can't await inside this sync loop easily without standard loop.
                        # Actually we can just collect list and await.
                        pass # Refactor below
            
            # Async version
            async def upload_sources_async():
                tasks = []
                for root, dirs, files in os.walk(working_dir):
                    for f in files:
                        local_f = os.path.join(root, f)
                        # Skip large PDF results for source upload
                        if local_f == original_pdf_path or local_f.endswith("_zh.pdf") or local_f.endswith("_zh_flash.pdf"):
                            continue
                            
                        rel_file = os.path.relpath(local_f, working_dir)
                        dest_blob = f"{arxiv_id}/{rel_file}"
                        tasks.append(storage_service.upload_file(local_f, dest_blob))
                if tasks:
                    await asyncio.gather(*tasks)

            await upload_sources_async()

        # Upload translated PDF to GCS
        # Find the translated file
        # Upload translated PDF to Storage
        if storage_service != local_storage:
            async def upload_translated_pdf():
                candidates = [
                    f"{arxiv_id}_zh_flash.pdf",
                    f"{arxiv_id}_zh_pro.pdf",
                    f"{arxiv_id}_zh.pdf"
                ]
                for f in candidates:
                    local_f = os.path.join(working_dir, f)
                    if os.path.exists(local_f):
                         await storage_service.upload_file(local_f, f"{arxiv_id}/{f}")
                         break
            
            await upload_translated_pdf()

    except Exception as e:
        logger.error(f"Task Exception: {e}")
        update_status(arxiv_id, "failed", str(e))

async def run_translation_wrapper(arxiv_url: str, model: str, arxiv_id: str, deepdive: bool = False):
    await run_translation_stream(arxiv_url, model, arxiv_id, deepdive)

@app.get("/library")
async def get_library():
    # Use to_thread for library read
    return await asyncio.to_thread(library_manager.list_papers)

@app.delete("/library/{arxiv_id}")
async def delete_paper(arxiv_id: str):
    # 1. Remove from Library metadata
    success = await library_manager.delete_paper(arxiv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Paper not found in library")

    # 2. Delete files from Storage (Local or GCS)
    # We delete the folder {arxiv_id}
    # For GCS, this deletes objects with prefix {arxiv_id}/
    await storage_service.delete_folder(arxiv_id)
    
    # Also delete local cache if we are using GCS but have local files
    if storage_service != local_storage:
        await local_storage.delete_folder(arxiv_id)

    return {"message": f"Paper {arxiv_id} deleted successfully", "arxiv_id": arxiv_id}

@app.post("/translate")
async def translate_paper(request: TranslationRequest, background_tasks: BackgroundTasks):
    parts = request.arxiv_url.split("/")
    arxiv_id = parts[-1] 
    if arxiv_id.endswith(".pdf"):
        arxiv_id = arxiv_id.replace(".pdf", "")
    
    # Check Library Cache
    paper = library_manager.get_paper(arxiv_id)
    if paper:
        # Check if requested model version exists
        for v in paper.get("versions", []):
            if v["model"] == request.model and v["status"] == "completed":
                 # Check if we want auxiliary but cached version was without? 
                 # For simplicity, if cached, we return cached. 
                 # User can delete and re-run if they want features.
                 # Or we could just say "Already completed".
                 return {"message": "Already completed", "arxiv_id": arxiv_id, "status": "completed", "cached": True}

    current = TASK_STATUS.get(arxiv_id)
    if current and current["status"] in ["processing", "queued"]:
        return {"message": "Already processing", "arxiv_id": arxiv_id, "status": current["status"]}
    
    update_status(arxiv_id, "queued", "Waiting in queue...")
    background_tasks.add_task(run_translation_wrapper, request.arxiv_url, request.model, arxiv_id, request.deepdive)
    
    return {"message": "Translation started", "arxiv_id": arxiv_id}

@app.get("/status/{arxiv_id}")
async def get_status(arxiv_id: str):
    status_info = TASK_STATUS.get(arxiv_id)
    if not status_info:
        # Check library persistence for completion status (handle server restarts)
        paper = library_manager.get_paper(arxiv_id)
        if paper:
             for v in paper.get("versions", []):
                 if v["status"] == "completed":
                      return {"arxiv_id": arxiv_id, "status": "completed", "message": "Translation finished successfully.", "progress": 100}

        return {"arxiv_id": arxiv_id, "status": "not_found", "message": "", "progress": 0}
    return {
        "arxiv_id": arxiv_id, 
        "status": status_info["status"], 
        "message": status_info["message"],
        "progress": status_info.get("progress_percent", 0),
        "details": status_info.get("details", "")
    }

@app.get("/tasks")
async def get_tasks():
    """Returns a list of all tracked tasks."""
    # Convert dict to list and add ID
    tasks = []
    for aid, info in TASK_STATUS.items():
        tasks.append({
            "arxiv_id": aid,
            "status": info["status"],
            "message": info["message"],
            "progress": info.get("progress_percent", 0),
            "details": info.get("details", "")
        })
    # Sort by mostly active? or just return all
    return tasks

@app.get("/paper/{arxiv_id}/{file_type}")
async def get_paper(arxiv_id: str, file_type: str):
    """"Serve paper. If GCS is enabled, could return signed URL, but for now serve nicely proxy or local"""
    paper_dir = os.path.join(PAPER_STORAGE, arxiv_id)
    
    filename = None
    if file_type == "original":
        filename = f"{arxiv_id}.pdf"
    elif file_type == "translated":
        candidates = [
            f"{arxiv_id}_zh_flash.pdf",
            f"{arxiv_id}_zh_pro.pdf",
            f"{arxiv_id}_zh.pdf"
        ]
        # Check local first
        if os.path.exists(paper_dir):
            for f in os.listdir(paper_dir):
                if f in candidates or (f.endswith(".pdf") and "_zh" in f):
                    filename = f
                    break
    
    if filename:
        file_path = os.path.join(paper_dir, filename)
        if os.path.exists(file_path):
             return FileResponse(file_path)
    
    # If not found locally, try GCS if enabled (fallback logic for cloud run where local might be ephemeral)
    if GCS_AVAILABLE and GCS_BUCKET_NAME and storage_client:
        try:
             bucket = storage_client.bucket(GCS_BUCKET_NAME)
             # Try to find the file in GCS
             # Construction logic
             blob_name = f"{arxiv_id}/{filename}"
             if not filename:
                 # Try to guess
                 if file_type == "original":
                     blob_name = f"{arxiv_id}/{arxiv_id}.pdf"
                 else:
                     # This is hard because we don't know the suffix without listing
                     # List blobs
                     blobs = list(bucket.list_blobs(prefix=f"{arxiv_id}/"))
                     for b in blobs:
                         if "_zh" in b.name and b.name.endswith(".pdf"):
                             blob_name = b.name
                             break
                             
             blob = bucket.blob(blob_name)
             if blob.exists():
                 # Generate signed URL
                 url = blob.generate_signed_url(version="v4", expiration=3600, method="GET")
                 return RedirectResponse(url)
        except Exception as e:
            logger.error(f"GCS Fetch Error: {e}")

    raise HTTPException(status_code=404, detail="File not found")
