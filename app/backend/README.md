# ReadPaper Backend

The backend service for ReadPaper, built with **FastAPI**. It orchestrates the translation process by invoking the `arxiv-translator` library and managing task status.

## API Endpoints

### `POST /translate`

Submit a paper for translation.

**Request:**
```json
{
  "arxiv_url": "https://arxiv.org/abs/2101.00001"
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

Check the progress of a translation task.

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
