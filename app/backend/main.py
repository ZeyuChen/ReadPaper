import os
import sys
import shutil
import asyncio
import subprocess
from dotenv import load_dotenv

# Load environment variables from .env file
# Load environment variables from .env file
load_dotenv()
import sys
print(f"DEBUG: sys.path: {sys.path}")
try:
    import feedparser
    print(f"DEBUG: feedparser imported successfully: {feedparser}")
except ImportError as e:
    print(f"DEBUG: feedparser import failed: {e}")
    # continue to let it fail later or explore why

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, TypedDict, Optional, List

from .services.storage import LocalStorageService, GCSStorageService, StorageService
from .services.library import LibraryManager
from .services.cache import TranslationCache
from .services.auth import get_current_user
from .services.rate_limiter import check_translate_rate_limit
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

# ── Task Status: GCS-backed or in-memory ─────────────────────────────────────
# In Cloud Run, multiple instances share NO in-memory state.
# We persist status as a tiny JSON file in GCS: _status/{task_key}.json
# In local/non-GCS mode we fall back to an in-memory dict.
_LOCAL_TASK_STATUS: Dict[str, TaskStatus] = {}


def _status_key_to_gcs_path(task_key: str) -> str:
    """GCS object path for the given task_key status file."""
    # task_key is 'user_id:arxiv_id' — replace ':' so it's a valid GCS name segment
    safe = task_key.replace(":", "__")
    return f"_status/{safe}.json"


def _read_task_status(task_key: str) -> dict:
    """Read status from GCS (or in-memory dict)."""
    if STORAGE_TYPE == "gcs" and GCS_BUCKET_NAME:
        import json
        from google.cloud import storage as gcs_lib
        from google.api_core.exceptions import NotFound
        try:
            client = gcs_lib.Client()
            blob = client.bucket(GCS_BUCKET_NAME).blob(_status_key_to_gcs_path(task_key))
            return json.loads(blob.download_as_text())
        except NotFound:
            return {}
        except Exception as e:
            logger.warning(f"GCS status read error for {task_key}: {e}")
            return {}
    return _LOCAL_TASK_STATUS.get(task_key, {})


# Shared thread pool for non-blocking GCS status I/O
_STATUS_EXECUTOR = None
_GCS_CLIENT_CACHE = None


def _get_gcs_client():
    global _GCS_CLIENT_CACHE
    if _GCS_CLIENT_CACHE is None:
        from google.cloud import storage as gcs_lib
        _GCS_CLIENT_CACHE = gcs_lib.Client()
    return _GCS_CLIENT_CACHE


def _get_executor():
    global _STATUS_EXECUTOR
    if _STATUS_EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor
        _STATUS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gcs_status")
    return _STATUS_EXECUTOR


def _write_task_status(task_key: str, data: dict) -> None:
    """Write status to GCS (non-blocking fire-and-forget) or in-memory."""
    if STORAGE_TYPE == "gcs" and GCS_BUCKET_NAME:
        import json

        def _do_write():
            try:
                client = _get_gcs_client()
                blob = client.bucket(GCS_BUCKET_NAME).blob(_status_key_to_gcs_path(task_key))
                blob.upload_from_string(json.dumps(data), content_type="application/json")
            except Exception as e:
                logger.warning(f"GCS status write error for {task_key}: {e}")

        _get_executor().submit(_do_write)  # fire-and-forget
    else:
        _LOCAL_TASK_STATUS[task_key] = data


# Compat shim: allow code that reads TASK_STATUS[key] to work transparently
class _TaskStatusProxy:
    """A dict-like proxy that persists reads/writes to GCS or memory."""
    def get(self, key, default=None):
        result = _read_task_status(key)
        return result if result else default

    def __getitem__(self, key):
        return _read_task_status(key)

    def __setitem__(self, key, value):
        _write_task_status(key, value)

    def __contains__(self, key):
        return bool(_read_task_status(key))

    def items(self):
        """Return (key, value) pairs from in-memory status (local mode only)."""
        return _LOCAL_TASK_STATUS.items()

    def keys(self):
        return _LOCAL_TASK_STATUS.keys()


TASK_STATUS = _TaskStatusProxy()


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

# --- Startup Configuration Logging ---
logger.info("="*50)
logger.info("READPAPER BACKEND STARTUP")
logger.info(f"Environment: {'CLOUD RUN' if IS_CLOUD_RUN else 'LOCAL'}")
logger.info(f"Storage Mode: {STORAGE_TYPE.upper()}")
if STORAGE_TYPE == 'local':
    logger.info(f"Storage Path: {PAPER_STORAGE_ROOT}")
elif STORAGE_TYPE == 'gcs':
    logger.info(f"GCS Bucket:   {GCS_BUCKET_NAME}")
logger.info("="*50)
# -------------------------------------

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
    if STORAGE_TYPE == "gcs":
        logger.warning("STORAGE_TYPE is 'gcs' but GCS_BUCKET_NAME is missing. Falling back to Local.")
    logger.info("Using Local Storage Service.")
    root_storage = LocalStorageService(PAPER_STORAGE_ROOT)

# Global translation cache (shared across all users)
translation_cache = TranslationCache(root_storage)

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

def update_status(task_key: str, status: str, message: str = "", progress: int = 0, details: str = ""):
    current = TASK_STATUS.get(task_key, {})
    current_pct = current.get("progress_percent", 0)

    # ── Strict monotonic progress (high-water-mark) ─────────────────────
    # During "processing", progress must NEVER decrease.
    # If caller passes 0, inherit the current value.
    # If caller passes a non-zero value lower than current, clamp to current.
    if status == "processing":
        if progress == 0:
            progress = current_pct
        else:
            progress = max(progress, current_pct)

    logger.info(f"[{task_key}] {status}: {message} ({progress}%)")

    TASK_STATUS[task_key] = {
        "status": status,
        "message": message,
        "progress_percent": progress,
        "details": details,
        # Preserve per-file status across status updates
        "files": current.get("files", {}),
        "compile_log": current.get("compile_log", ""),
        # Preserve token counts across status updates
        "total_in_tokens": current.get("total_in_tokens", 0),
        "total_out_tokens": current.get("total_out_tokens", 0),
    }


def update_file_status(task_key: str, filename: str, file_status: str,
                       batches_done: int = None, batches_total: int = None):
    """Update the status of a single .tex file within the TASK_STATUS files dict."""
    current = TASK_STATUS.get(task_key, {})
    files = dict(current.get("files", {}))
    entry = dict(files.get(filename, {"status": "pending", "batches_done": 0, "batches_total": 0}))
    entry["status"] = file_status
    if batches_done is not None:
        entry["batches_done"] = batches_done
    if batches_total is not None:
        entry["batches_total"] = batches_total
    files[filename] = entry
    TASK_STATUS[task_key] = {**current, "files": files}

# Track per-file integrity status for cache decisions
_FILE_INTEGRITY: dict[str, dict[str, bool]] = {}

async def run_translation_stream(arxiv_url: str, model: str, arxiv_id: str, user_id: str, storage_service: StorageService, library_manager: LibraryManager):
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
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if IS_CLOUD_RUN:
            env["ARXIV_TRANSLATOR_LOG_DIR"] = "/tmp/logs"
        else:
            env["ARXIV_TRANSLATOR_LOG_DIR"] = os.path.abspath(os.path.join(BASE_DIR, "logs")) 
        project_root = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        # ── Critical: drain stderr concurrently to prevent pipe-buffer deadlock ──
        # If we only read stdout, the subprocess can fill the stderr OS pipe buffer
        # (~64 KB) and block indefinitely, freezing the entire IPC stream.
        stderr_lines: list[str] = []

        async def drain_stderr():
            assert process.stderr is not None
            while True:
                raw = await process.stderr.readline()
                if not raw:
                    break
                line_text = raw.decode("utf-8", errors="replace").rstrip()
                stderr_lines.append(line_text)
                # Cap in-memory collection to last 200 lines
                if len(stderr_lines) > 200:
                    stderr_lines.pop(0)
                # Elevate to INFO so translation errors are visible in Cloud Run logs
                logger.info(f"[STDERR] {line_text}")

        stderr_task = asyncio.create_task(drain_stderr())

        # ── Stream and parse stdout IPC messages ──────────────────────────────
        status_map = {
            "DOWNLOADING": (5,  "Downloading source package..."),
            "EXTRACTING":  (8,  "Extracting source files..."),
            "PRE_FLIGHT":  (12, "Running pre-flight checks..."),
            "TRANSLATING": (15, "Translating..."),
            "POST_PROCESSING": (86, "Cleaning up LaTeX..."),
            "COMPILING":   (92, "Compiling final PDF (pdfLaTeX)..."),
            "COMPLETED":   (100, "Done"),
            "COMPLETED_WITH_WARNINGS": (100, "Done (with warnings)"),
            "WARN":  (0, "Warning"),
            "FAILED": (0, "Failed"),
        }

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode('utf-8').strip()
            if line.startswith("PROGRESS:"):
                # Parse: PROGRESS:CODE:rest  (split at most twice)
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                code, rest = parts[1], parts[2]

                # Fetch current progress to ensure monotonicity
                current_status = TASK_STATUS.get(task_key, {})
                current_pct = current_status.get("progress_percent", 0)

                # ── Per-file FILE_LIST: initialise files dict ──────────────
                if code == "FILE_LIST":
                    names = [n.strip() for n in rest.split("|") if n.strip()]
                    files = {n: {"status": "pending", "batches_done": 0, "batches_total": 0} for n in names}
                    current_state = TASK_STATUS.get(task_key, {})
                    TASK_STATUS[task_key] = {**current_state, "files": files}

                # ── Per-file FILE_DONE ──────────────────────────────────────
                elif code == "FILE_DONE":
                    fd_parts = rest.split(":", 1)
                    if len(fd_parts) == 2:
                        fname, outcome = fd_parts
                        update_file_status(
                            task_key, fname.strip(),
                            "done" if outcome.strip() == "ok" else "failed"
                        )

                # ── Per-file integrity status ──────────────────────────────
                elif code == "INTEGRITY":
                    # Format: INTEGRITY:{filename}:{valid|invalid}
                    try:
                        i_parts = rest.split(":", 1)
                        if len(i_parts) == 2:
                            i_fname, i_status = i_parts[0].strip(), i_parts[1].strip()
                            _FILE_INTEGRITY.setdefault(task_key, {})[i_fname] = (i_status == "valid")
                            logger.info(f"[integrity] {i_fname}: {i_status}")
                    except Exception:
                        pass


                # ── Per-file token summary ─────────────────────────────────
                elif code == "TOKENS_TOTAL":
                    # Format: TOKENS_TOTAL:{in}:{out}:{filename}
                    try:
                        tp = rest.split(":", 2)
                        in_t, out_t = int(tp[0]), int(tp[1])
                        fname_t = tp[2] if len(tp) > 2 else ""
                        current_state = TASK_STATUS.get(task_key, {})
                        prev_in = current_state.get("total_in_tokens", 0)
                        prev_out = current_state.get("total_out_tokens", 0)
                        new_in = prev_in + in_t
                        new_out = prev_out + out_t
                        TASK_STATUS[task_key] = {
                            **current_state,
                            "total_in_tokens": new_in,
                            "total_out_tokens": new_out,
                        }
                        tok_msg = (
                            f"✅ {fname_t} done | "
                            f"Gemini In: {new_in:,} / Out: {new_out:,} tokens total"
                        )
                        update_status(task_key, "processing", tok_msg, current_pct)
                        logger.info(f"[tokens] {fname_t}: in={in_t} out={out_t} | total in={new_in} out={new_out}")
                    except Exception:
                        pass

                # ── Final total tokens summary ─────────────────────────────
                elif code == "TOKENS_SUMMARY":
                    # Format: TOKENS_SUMMARY:{total_in}:{total_out}
                    try:
                        tp = rest.split(":", 1)
                        total_in, total_out = int(tp[0]), int(tp[1])
                        current_state = TASK_STATUS.get(task_key, {})
                        TASK_STATUS[task_key] = {
                            **current_state,
                            "total_in_tokens": total_in,
                            "total_out_tokens": total_out,
                        }
                        logger.info(f"[tokens-summary] Final totals: in={total_in:,} out={total_out:,}")
                    except Exception:
                        pass

                # ── File-level TRANSLATING:count:total:message ─────────────
                elif code == "TRANSLATING":
                    try:
                        p_parts = rest.split(":", 2)
                        if len(p_parts) >= 3:
                            count, total = int(p_parts[0]), int(p_parts[1])
                            msg = p_parts[2]
                            pct = max(15 + int((count / total) * 70), current_pct) if total > 0 else current_pct
                            update_status(task_key, "processing", f"Translating: {msg}", pct)
                        else:
                            update_status(task_key, "processing", f"Translating: {rest}", current_pct)
                    except Exception:
                        update_status(task_key, "processing", f"Translating: {rest}", current_pct)


                # ── Standard status_map codes ──────────────────────────────
                elif code in status_map:
                    prog, default_msg = status_map[code]
                    if code == "COMPLETED":
                        update_status(task_key, "processing", "Finalizing upload...", 99)
                    elif code == "COMPLETED_WITH_WARNINGS":
                        update_status(task_key, "processing", "Finalizing upload (with warnings)...", 99, rest)
                    elif code == "WARN":
                        update_status(task_key, "processing", rest, current_pct, rest)
                    elif code == "FAILED":
                        current_state = TASK_STATUS.get(task_key, {})
                        TASK_STATUS[task_key] = {**current_state, "compile_log": rest}
                        update_status(task_key, "failed", rest, 0)
                    else:
                        prog = max(prog, current_pct)
                        display_msg = rest.strip() if rest.strip() else default_msg
                        update_status(task_key, "processing", display_msg, prog)
                else:
                    # Unknown code — surface the raw message
                    update_status(task_key, "processing", rest, current_pct)

                # ── Early upload of original tex files after EXTRACTING ────
                # This lets the frontend preview original .tex files even while
                # translation is still running.
                if code == "EXTRACTING" and "Analyzing" in rest:
                    # Extraction just finished — upload source/ tex files now
                    ws_candidates = [os.path.join(work_root, f"workspace_{arxiv_id}")]
                    # Also try versioned workspace dirs
                    if os.path.isdir(work_root):
                        for entry in os.listdir(work_root):
                            if entry.startswith(f"workspace_{arxiv_id}") and os.path.isdir(os.path.join(work_root, entry)):
                                ws_candidates.append(os.path.join(work_root, entry))
                    for ws_dir in ws_candidates:
                        source_dir = os.path.join(ws_dir, "source")
                        if os.path.isdir(source_dir):
                            upload_count = 0
                            for root_d, _, files_list in os.walk(source_dir):
                                for fname in files_list:
                                    if fname.endswith(".tex"):
                                        local_tex = os.path.join(root_d, fname)
                                        rel_path = os.path.relpath(local_tex, source_dir)
                                        gcs_key = f"{arxiv_id}/tex/original/{rel_path}"
                                        try:
                                            await storage_service.upload_file(local_tex, gcs_key)
                                            upload_count += 1
                                        except Exception as tex_e:
                                            logger.warning(f"Early tex upload failed: {gcs_key}: {tex_e}")
                            if upload_count > 0:
                                logger.info(f"Early-uploaded {upload_count} original tex files")
                            break  # Found the workspace, stop searching

        # Wait for stderr drainer to finish
        await stderr_task

        return_code = await process.wait()

        if return_code != 0:
            # Use collected stderr lines for a meaningful error message
            err_snippet = "\n".join(stderr_lines[-20:]) if stderr_lines else "(no stderr output)"
            err_preview = err_snippet[:2000]
            update_status(task_key, "failed", f"Translator process exited with code {return_code}.\n{err_preview}")
            return

        # 3. Upload Results to User Storage
        # Expected outputs in work_root (CWD) or workspace directory
        workspace_dir = os.path.join(work_root, f"workspace_{arxiv_id}")
        
        # Recursively search entire work_root tree for any translated PDF
        # (handles nested workspace dirs and rescue mode output paths)
        found_pdf_path = None
        for dirpath, _, filenames in os.walk(work_root):
            for f in filenames:
                if f.endswith(".pdf") and ("_zh" in f or "translated" in f.lower()):
                    found_pdf_path = os.path.join(dirpath, f)
                    logger.info(f"Found translated PDF: {found_pdf_path}")
                    break
            if found_pdf_path:
                break

        # Last resort: find ANY pdf that isn't the original (might be rescue output)
        if not found_pdf_path:
            original_pdf = f"{arxiv_id}.pdf"
            for dirpath, _, filenames in os.walk(work_root):
                for f in filenames:
                    if f.endswith(".pdf") and f != original_pdf:
                        found_pdf_path = os.path.join(dirpath, f)
                        logger.info(f"Found fallback PDF (rescue): {found_pdf_path}")
                        break
                if found_pdf_path:
                    break

        if found_pdf_path:
             pdf_filename = os.path.basename(found_pdf_path)
             await storage_service.upload_file(found_pdf_path, f"{arxiv_id}/{pdf_filename}")

             # ── Upload .tex source files for long-term preview ───────────────
             # Walk source/ (original) and source_zh/ (translated) and upload
             # every .tex file to GCS at {arxiv_id}/tex/original/ and
             # {arxiv_id}/tex/translated/ so the frontend can preview them
             # via the /paper/{arxiv_id}/texfile endpoint.
             #
             # The subprocess creates workspace_<full_arxiv_id> which may include
             # a version suffix (e.g., workspace_2602.04705v1) while the backend
             # only has the base ID (2602.04705). Search dynamically.
             workspace_dir_tex = os.path.join(work_root, f"workspace_{arxiv_id}")
             if not os.path.exists(workspace_dir_tex):
                 # Try to find the actual workspace dir (handles version suffix mismatch)
                 for entry in os.listdir(work_root):
                     full = os.path.join(work_root, entry)
                     if os.path.isdir(full) and entry.startswith(f"workspace_{arxiv_id}"):
                         workspace_dir_tex = full
                         logger.info(f"Found workspace with version suffix: {entry}")
                         break
             logger.info(f"Looking for tex files in workspace: {workspace_dir_tex}")
             logger.info(f"workspace exists: {os.path.exists(workspace_dir_tex)}")
             if os.path.exists(workspace_dir_tex):
                 logger.info(f"workspace contents: {os.listdir(workspace_dir_tex)}")
             tex_upload_count = 0
             for tex_variant, subdir in (("original", "source"), ("translated", "source_zh")):
                 tex_dir = os.path.join(workspace_dir_tex, subdir)
                 logger.info(f"Checking tex dir: {tex_dir} exists={os.path.isdir(tex_dir)}")
                 if os.path.isdir(tex_dir):
                     for root_d, _, files in os.walk(tex_dir):
                         for fname in files:
                             if fname.endswith(".tex"):
                                 local_tex = os.path.join(root_d, fname)
                                 # Use relative path from tex_dir to preserve subdirectory structure
                                 rel_path = os.path.relpath(local_tex, tex_dir)
                                 gcs_key = f"{arxiv_id}/tex/{tex_variant}/{rel_path}"
                                 try:
                                     await storage_service.upload_file(local_tex, gcs_key)
                                     tex_upload_count += 1
                                 except Exception as tex_e:
                                     logger.warning(f"tex upload failed: {gcs_key}: {tex_e}")
             logger.info(f"Uploaded {tex_upload_count} tex files total")

             # ── Write translated files to global cache ─────────────────────
             # Only cache files that passed integrity validation
             file_integrity = _FILE_INTEGRITY.get(task_key, {})
             source_zh_tex_dir = os.path.join(workspace_dir_tex, "source_zh")
             if os.path.isdir(source_zh_tex_dir):
                 cache_count = 0
                 for root_d, _, cache_files in os.walk(source_zh_tex_dir):
                     for fname in cache_files:
                         if fname.endswith(".tex"):
                             is_valid = file_integrity.get(fname, False)
                             if is_valid:
                                 local_path = os.path.join(root_d, fname)
                                 try:
                                     with open(local_path, 'r', encoding='utf-8', errors='ignore') as cf:
                                         translated_content = cf.read()
                                     await translation_cache.put_cache(
                                         arxiv_id, fname, translated_content,
                                         is_valid=True, model=model,
                                     )
                                     cache_count += 1
                                 except Exception as cache_e:
                                     logger.warning(f"Cache write failed for {fname}: {cache_e}")
                             else:
                                 logger.info(f"Skipping cache for {fname} (integrity={is_valid})")
                 if cache_count > 0:
                     await translation_cache.mark_complete(arxiv_id)
                     logger.info(f"Cached {cache_count} valid translated files for {arxiv_id}")
             # Clean up integrity tracking
             _FILE_INTEGRITY.pop(task_key, None)

             # Update Library
             meta = fetch_arxiv_metadata(arxiv_id)
             await library_manager.add_paper(
                 arxiv_id, model, 
                 meta.get("title", arxiv_id), 
                 meta.get("abstract", ""), 
                 meta.get("authors", []), 
                 meta.get("categories", [])
             )
             update_status(task_key, "completed", "Processing complete.", 100)
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

async def run_translation_wrapper(arxiv_url: str, model: str, arxiv_id: str, user_id: str, storage: StorageService, lib: LibraryManager):
    await run_translation_stream(arxiv_url, model, arxiv_id, user_id, storage, lib)

@app.get("/library")
async def get_library(library_manager: LibraryManager = Depends(get_library_manager)):
    # Returns papers for current user
    return await library_manager.list_papers()

@app.delete("/library/{arxiv_id}")
async def delete_paper(
    arxiv_id: str, 
    library_manager: LibraryManager = Depends(get_library_manager),
    storage_service: StorageService = Depends(get_storage_service),
    user_id: str = Depends(get_current_user),
):
    success = await library_manager.delete_paper(arxiv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Delete all user files (PDFs, tex files, etc.)
    await storage_service.delete_folder(arxiv_id)
    
    # Clean up status cache in GCS and in-memory
    task_key = f"{user_id}:{arxiv_id}"
    # Remove from in-memory status dict
    TASK_STATUS.pop(task_key, None)
    # Remove GCS status file
    if GCS_BUCKET_NAME:
        try:
            status_path = _status_key_to_gcs_path(task_key)
            from google.cloud import storage as gcs_storage
            client = gcs_storage.Client()
            blob = client.bucket(GCS_BUCKET_NAME).blob(status_path)
            if blob.exists():
                blob.delete()
                logger.info(f"Deleted GCS status cache: {status_path}")
        except Exception as e:
            logger.warning(f"Failed to delete status cache: {e}")
    
    logger.info(f"Deleted paper {arxiv_id} for user {user_id}: files + status cache")
    return {"message": "Deleted"}

@app.get("/search")
async def search_papers(q: str, max_results: int = 8):
    """
    Search arXiv papers by keyword/title query.
    Returns a list of matching papers with metadata.
    """
    try:
        import urllib.parse
        query = urllib.parse.quote(q)
        url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}&sortBy=relevance"
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1]
            results.append({
                "arxiv_id": arxiv_id,
                "title": entry.title.replace("\n", " ").strip(),
                "abstract": entry.summary.replace("\n", " ").strip()[:300] + "...",
                "authors": [a.name for a in getattr(entry, "authors", [])],
                "categories": [t.term for t in getattr(entry, "tags", [])],
                "published": getattr(entry, "published", ""),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
            })
        return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/metadata/{arxiv_id}")
async def get_metadata(arxiv_id: str):
    """Fetch paper metadata from arXiv by ID — used for preview before translation."""
    meta = fetch_arxiv_metadata(arxiv_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Paper not found on arXiv")
    meta["arxiv_id"] = arxiv_id
    meta["url"] = f"https://arxiv.org/abs/{arxiv_id}"
    return meta

@app.post("/translate")
async def translate_paper(
    request: TranslationRequest, 
    background_tasks: BackgroundTasks,
    user_id: str = Depends(check_translate_rate_limit),
    storage_service: StorageService = Depends(get_storage_service),
    library_manager: LibraryManager = Depends(get_library_manager)
):
    parts = request.arxiv_url.split("/")
    # Strip .pdf extension but PRESERVE version suffix (e.g. 2602.15763v1)
    # Version is needed for cache keying — different versions have different content
    arxiv_id = parts[-1].replace(".pdf", "")
    # Extract base ID (without version) for library/storage lookups
    import re as _re
    arxiv_id_base = _re.sub(r'v\d+$', '', arxiv_id)
    
    # Check Library (use base ID for library lookups)
    paper = await library_manager.get_paper(arxiv_id_base)
    if paper:
        # Simplified check: if exists, return it
        return {"message": "Already completed", "arxiv_id": arxiv_id_base, "status": "completed"}
    
    task_key = f"{user_id}:{arxiv_id_base}"

    # Guard against concurrent translations of the same paper
    existing = TASK_STATUS.get(task_key, {})
    if existing.get("status") in ("processing", "queued"):
        return {"message": "Already in progress", "arxiv_id": arxiv_id_base, "status": existing.get("status")}

    update_status(task_key, "queued", "Started")
    
    background_tasks.add_task(
        run_translation_wrapper, 
        request.arxiv_url, request.model, arxiv_id_base,
        user_id, storage_service, library_manager
    )
    
    return {"message": "Started", "arxiv_id": arxiv_id_base}

@app.get("/status/{arxiv_id}")
async def get_status(
    arxiv_id: str, 
    user_id: str = Depends(get_current_user)
):
    task_key = f"{user_id}:{arxiv_id}"
    # Use asyncio.to_thread so GCS network I/O doesn't block the event loop
    status = await asyncio.to_thread(_read_task_status, task_key)
    if not status:
        return {"status": "not_found"}
    return status

@app.get("/paper/{arxiv_id}/texfile")
async def get_tex_file(
    arxiv_id: str,
    name: str,
    type: str = "translated",
    storage_service: StorageService = Depends(get_storage_service),
    user_id: str = Depends(get_current_user),
):
    """
    Serve a .tex source file (original or translated) for preview in the frontend.

    Query params:
        name: filename (e.g. 'main.tex')
        type: 'original' or 'translated' (default: translated)

    Files are stored at {arxiv_id}/tex/{type}/{name} in user storage.
    """
    if type not in ("original", "translated"):
        raise HTTPException(status_code=400, detail="type must be 'original' or 'translated'")

    gcs_key = f"{arxiv_id}/tex/{type}/{name}"
    try:
        content_bytes = await storage_service.get_file(gcs_key)
        if content_bytes is None:
            raise HTTPException(status_code=404, detail=f"File not found: {gcs_key}")
        content = content_bytes.decode("utf-8", errors="replace")
        return {"filename": name, "type": type, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"tex file fetch failed ({gcs_key}): {e}")
        raise HTTPException(status_code=404, detail=f"File not available: {name}")

@app.get("/paper/{arxiv_id}/{file_type}")
async def get_paper(
    arxiv_id: str, 
    file_type: str,
    storage_service: StorageService = Depends(get_storage_service)
):
    """
    Serves the PDF file (original or translated) for a specific paper.
    Returns 404 (not 500) when a file is missing.
    """
    files = storage_service.list_files(f"{arxiv_id}/")
    target = None
    
    if file_type == "original":
        # Exact name: {arxiv_id}.pdf
        expected = f"{arxiv_id}/{arxiv_id}.pdf"
        if any(f == expected or f.endswith(f"/{arxiv_id}.pdf") for f in files):
            target = expected
        elif files:
            # Fallback: any PDF that matches the arxiv_id exactly
            for f in files:
                if os.path.basename(f) == f"{arxiv_id}.pdf":
                    target = f"{arxiv_id}/{os.path.basename(f)}"
                    break

    elif file_type == "translated":
        # Match any translated PDF: prefers _zh suffix, accepts any non-original PDF
        original_name = f"{arxiv_id}.pdf"
        best = None
        fallback = None
        for f in files:
            basename = os.path.basename(f)
            if not basename.endswith(".pdf"):
                continue
            if basename == original_name:
                continue  # Skip the original
            if "_zh" in basename:
                best = f"{arxiv_id}/{basename}"
                break  # Take first _zh match
            elif fallback is None:
                fallback = f"{arxiv_id}/{basename}"
        target = best or fallback
    
    if not target:
        raise HTTPException(status_code=404, detail=f"{file_type} PDF not found for {arxiv_id}")

    if isinstance(storage_service, LocalStorageService):
        full_path = storage_service._get_full_path(target)
        if not os.path.exists(full_path):
            logger.warning(f"PDF missing from local storage: {full_path}")
            raise HTTPException(
                status_code=404, 
                detail=f"PDF file no longer available (server may have restarted)"
            )
        return FileResponse(full_path, media_type="application/pdf")

    elif isinstance(storage_service, GCSStorageService):
        gcs_path = storage_service._get_gcs_path(target)
        blob = storage_service.bucket.blob(gcs_path)
        try:
            exists = await asyncio.to_thread(blob.exists)
            if not exists:
                raise HTTPException(status_code=404, detail="PDF not found in cloud storage")
            # Stream the blob content directly — avoids needing a private key for signed URLs.
            # Cloud Run's service account has Storage Object Viewer access, so this works.
            filename = os.path.basename(target)
            blob_bytes = await asyncio.to_thread(blob.download_as_bytes)
            return StreamingResponse(
                iter([blob_bytes]),
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"GCS blob download failed: {e}")
            raise HTTPException(status_code=500, detail=f"Could not read file from cloud storage: {str(e)}")
            
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


# ── Admin Endpoints ─────────────────────────────────────────────────────────

SUPER_ADMIN_EMAIL = "chinachenzeyu@gmail.com"

async def require_admin(user_id: str = Depends(get_current_user)) -> str:
    """
    Dependency: only allows the super-admin user through.
    user_id is the verified Google email from the JWT.
    Raises HTTP 403 for all other users.
    """
    if user_id != SUPER_ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


async def _list_all_user_ids() -> list[str]:
    """
    Enumerate all user IDs that have stored data.
    Works for both GCS and local storage modes.
    """
    user_ids = []
    if STORAGE_TYPE == "gcs" and GCS_BUCKET_NAME and isinstance(root_storage, GCSStorageService):
        # GCS: list blobs with prefix="users/" and delimiter="/" to get top-level user folders
        client = root_storage.client
        iterator = client.list_blobs(GCS_BUCKET_NAME, prefix="users/", delimiter="/")
        _ = list(iterator)  # force iteration to populate .prefixes
        for prefix in (iterator.prefixes or []):
            # Each prefix looks like "users/user@email.com/"
            uid = prefix.removeprefix("users/").rstrip("/")
            if uid:
                user_ids.append(uid)
    else:
        # Local storage: scan PAPER_STORAGE_ROOT/users/ directories
        users_dir = os.path.join(PAPER_STORAGE_ROOT, "users")
        if os.path.isdir(users_dir):
            user_ids = [
                d for d in os.listdir(users_dir)
                if os.path.isdir(os.path.join(users_dir, d))
            ]
    return sorted(user_ids)


@app.get("/admin/papers")
async def admin_list_all_papers(admin_id: str = Depends(require_admin)):
    """
    Admin endpoint: aggregate all papers across all users.
    Returns: list of paper dicts, each enriched with a `user_id` field.
    """
    user_ids = await _list_all_user_ids()
    result = []
    for uid in user_ids:
        try:
            user_storage = root_storage.get_user_storage(uid)
            lib = LibraryManager(user_storage)
            papers = await lib.list_papers()
            for paper in papers:
                result.append({"user_id": uid, **paper})
        except Exception as e:
            logger.warning(f"Could not load library for user {uid}: {e}")
    return result


@app.get("/admin/stats")
async def admin_stats(admin_id: str = Depends(require_admin)):
    """
    Admin endpoint: high-level stats — total users & papers.
    """
    user_ids = await _list_all_user_ids()
    total_papers = 0
    for uid in user_ids:
        try:
            user_storage = root_storage.get_user_storage(uid)
            lib = LibraryManager(user_storage)
            papers = await lib.list_papers()
            total_papers += len(papers)
        except Exception:
            pass
    return {
        "total_users": len(user_ids),
        "total_papers": total_papers,
        "user_ids": user_ids,
    }

