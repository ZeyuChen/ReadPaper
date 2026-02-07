import os
import shutil
import subprocess
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, TypedDict, Optional

# Try to import GCS client
try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

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
PAPER_STORAGE = os.path.join(PROJECT_ROOT, "paper_storage")
os.makedirs(PAPER_STORAGE, exist_ok=True)

# GCS Config
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
storage_client = None
if GCS_AVAILABLE and GCS_BUCKET_NAME:
    try:
        storage_client = storage.Client() 
        print(f"GCS Storage enabled. Bucket: {GCS_BUCKET_NAME}")
    except Exception as e:
        print(f"Failed to initialize GCS client: {e}")

# Library Persistence
LIBRARY_FILE = os.path.join(PROJECT_ROOT, "library.json")
import json
import feedparser
import urllib.request
from datetime import datetime

class LibraryManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def add_paper(self, arxiv_id: str, model: str, title: str = "", abstract: str = "", authors: list = [], categories: list = []):
        self._load() # Reload to get latest
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
             # Update metadata if missing
             if title and not self.data[arxiv_id].get("title"): self.data[arxiv_id]["title"] = title
             if abstract and not self.data[arxiv_id].get("abstract"): self.data[arxiv_id]["abstract"] = abstract
             if authors and not self.data[arxiv_id].get("authors"): self.data[arxiv_id]["authors"] = authors
             if categories and not self.data[arxiv_id].get("categories"): self.data[arxiv_id]["categories"] = categories
        
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
            
        self._save()

    def get_paper(self, arxiv_id: str):
        self._load()
        return self.data.get(arxiv_id)

    def list_papers(self):
        self._load()
        # Return list sorted by added_at desc
        papers = list(self.data.values())
        papers.sort(key=lambda x: x["added_at"], reverse=True)
        return papers

library_manager = LibraryManager(LIBRARY_FILE)

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
        print(f"Error fetching metadata: {e}")
        return {}

class TranslationRequest(BaseModel):
    arxiv_url: str
    model: str = "flash"

def update_status(arxiv_id: str, status: str, message: str = "", progress: int = 0, details: str = ""):
    print(f"[{arxiv_id}] {status}: {message} ({progress}%)")
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

def upload_to_gcs(local_path: str, destination_blob_name: str):
    """"Uploads a file to the bucket."""
    if not storage_client or not GCS_BUCKET_NAME:
        return
    try:
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_path)
        print(f"Uploaded {local_path} to gs://{GCS_BUCKET_NAME}/{destination_blob_name}")
    except Exception as e:
        print(f"Failed to upload to GCS: {e}")

async def run_translation_stream(arxiv_url: str, model: str, arxiv_id: str):
    """"
    Runs arxiv-translator and streams output to update status.
    """
    try:
        working_dir = os.path.join(PAPER_STORAGE, arxiv_id)
        os.makedirs(working_dir, exist_ok=True)
        
        # 1. Download Original PDF
        update_status(arxiv_id, "processing", "Downloading original PDF...", 5)
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        original_pdf_path = os.path.join(working_dir, f"{arxiv_id}.pdf")
        
        # Check GCS first for original (optional optimization, skip for checking existence logic complexity)
        # Just download locally for processing
        
        if not os.path.exists(original_pdf_path):
            proc = subprocess.run(
                ["curl", "-L", "-o", original_pdf_path, pdf_url], 
                capture_output=True, 
                text=True
            )
            if proc.returncode != 0:
                print(f"Failed to download PDF: {proc.stderr}")
                update_status(arxiv_id, "processing", "Failed to download original PDF (Non-fatal, continuing...)", 5)
        
        # Upload original PDF to GCS
        if os.path.exists(original_pdf_path):
            upload_to_gcs(original_pdf_path, f"{arxiv_id}/{arxiv_id}.pdf")

        # 2. Run arxiv-translator
        cmd = [
            "arxiv-translator",
            arxiv_url,
            "--model", model
        ]
        
        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read stdout line by line
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                line = line.strip()
                # Check for progress markers
                if line.startswith("PROGRESS:"):
                    # Format: PROGRESS:CODE:P1:P2:MSG or PROGRESS:CODE:MSG
                    # New: PROGRESS:TRANSLATING:<IDX>:<TOTAL>:<FILENAME>
                    # Old: PROGRESS:DOWNLOADING:<MSG>
                    
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
                                        print(f"DEBUG: Parsed progress {p}% for {fname}")
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
                            
                        else:
                            update_status(arxiv_id, "processing", rest)
                else:
                    # Log other output to console for debug
                    # print(f"CLI: {line}")
                    pass
        
        # Check return code
        if process.poll() != 0:
            stderr_out = process.stderr.read()
            print(f"Translation Error: {stderr_out}")
            task_s = TASK_STATUS.get(arxiv_id)
            if task_s and task_s["status"] != "failed":
                update_status(arxiv_id, "failed", f"Process exited with error: {stderr_out[:100]}...", 0, "Process error")

        # Final check if we missed COMPLETED marker but process succeeded
        task_s = TASK_STATUS.get(arxiv_id)
        if process.poll() == 0 and task_s and task_s["status"] != "completed" and task_s["status"] != "failed":
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
             
             library_manager.add_paper(arxiv_id, model, title=title, abstract=abstract, authors=authors, categories=categories)

        # Upload translated PDF to GCS
        # Find the translated file
        candidates = [
            f"{arxiv_id}_zh_flash.pdf",
            f"{arxiv_id}_zh_pro.pdf",
            f"{arxiv_id}_zh.pdf"
        ]
        for f in candidates:
            local_f = os.path.join(working_dir, f)
            if os.path.exists(local_f):
                upload_to_gcs(local_f, f"{arxiv_id}/{f}")
                break

    except Exception as e:
        print(f"Task Exception: {e}")
        update_status(arxiv_id, "failed", str(e))

async def run_translation_wrapper(arxiv_url: str, model: str, arxiv_id: str):
    await run_translation_stream(arxiv_url, model, arxiv_id)

@app.get("/library")
async def get_library():
    return library_manager.list_papers()

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
                 return {"message": "Already completed", "arxiv_id": arxiv_id, "status": "completed", "cached": True}

    current = TASK_STATUS.get(arxiv_id)
    if current and current["status"] in ["processing", "queued"]:
        return {"message": "Already processing", "arxiv_id": arxiv_id, "status": current["status"]}
    
    update_status(arxiv_id, "queued", "Waiting in queue...")
    background_tasks.add_task(run_translation_wrapper, request.arxiv_url, request.model, arxiv_id)
    
    return {"message": "Translation started", "arxiv_id": arxiv_id}

@app.get("/status/{arxiv_id}")
async def get_status(arxiv_id: str):
    status_info = TASK_STATUS.get(arxiv_id)
    if not status_info:
        return {"arxiv_id": arxiv_id, "status": "not_found", "message": "", "progress": 0}
    return {
        "arxiv_id": arxiv_id, 
        "status": status_info["status"], 
        "message": status_info["message"],
        "progress": status_info.get("progress_percent", 0),
        "details": status_info.get("details", "")
    }

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
            print(f"GCS Fetch Error: {e}")

    raise HTTPException(status_code=404, detail="File not found")
