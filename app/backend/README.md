# ReadPaper Backend

The backend service for ReadPaper, built with **FastAPI**. It orchestrates the translation process by invoking the `arxiv-translator` library and managing task status.

## API Endpoints

### `POST /translate`

Submit a paper for translation.

**Request:**
```json
{
  "arxiv_url": "https://arxiv.org/abs/2101.00001",
  "model": "flash",
  "deepdive": true
}
```

**Response:**
```json
{
    "message": "Translation started",
    "arxiv_id": "2101.00001",
    "status": "processing"
}
```

### `GET /status/{arxiv_id}`

Check the progress of a translation task. Returns granular status updates (e.g., "Translating: abstract.tex (50%)").

## 💻 Local Development

You can run the backend directly with Python or using Docker.

### Option 1: Python (Direct)

Requires a local installation of `latexmk` and `texlive` (or MacTeX) if you want to perform actual PDF compilations.

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn app.backend.main:app --reload
```

### Option 2: Docker (Recommended)

The Docker image includes a full TeX Live 2024 distribution, ensuring consistent compilation.

```bash
# Build
docker build -t readpaper-backend ./app/backend

# Run (mounting a local temp dir for persistence)
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -v /tmp/readpaper_storage:/tmp/paper_storage \
  readpaper-backend
```

## 🧩 Services

The backend is organized into modular services:

- **`arxiv_translator/`**: The core engine. Handles downloading source, cleaning LaTeX, translating via Gemini, and recompiling.
- **`services/storage.py`**: Abstract storage layer. Supports `LocalStorageService` (for dev/testing) and `GCSStorageService` (for production on Google Cloud).
- **`services/library.py`**: Manages the user's personal library of papers. Currently uses a simple JSON-based file persistence.
- **`services/auth.py`**: Handles user session validation (verifying Google ID Tokens passed from the frontend).

## Configuration

Environment Variables:
- `GEMINI_API_KEY`: Required for Gemini API access.
- `GCS_BUCKET_NAME`: (Optional) Google Cloud Storage bucket name for storing PDFs.
- `GOOGLE_CLOUD_PROJECT`: (Optional) GCP Project ID.

## Running Tests

```bash
# From project root
python -m pytest app/backend/tests
```
