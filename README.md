# ReadPaper: AI-Powered arXiv Paper Translator

**ReadPaper** is a cloud-native application that translates arXiv papers from English to Chinese (and other languages via Gemini) while preserving the original LaTeX layout. It features a modern split-view interface for reading the original and translated versions side-by-side.

## Features

- **High-Fidelity Translation**: Uses Google's **Gemini 1.5 Flash/Pro** models to translate LaTeX source code directly.
- **Split View Reading**: Compare original and translated PDFs instantly.
- **Concurrent Processing**: Multi-process translation for fast turnaround (8x speedup).
- **Cloud Ready**: Designed for Google Cloud Run with Firestore caching and GCS storage.
- **Robust Compilation**: automatic fixes for `minted` packages and duplicate labels.

## Project Structure

- `app/backend`: Python FastAPI service handling translation requests and arXiv interaction.
- `app/frontend`: Next.js application providing the user interface.
- `arxiv-translator`: Core library for downloading, translating, and recompiling arXiv papers.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Tectonic](https://tectonic-typesetting.github.io/) (LaTeX compiler) installed globally.
- Google Cloud Project with Gemini API enabled.

### Backend Setup

```bash
cd app/backend
pip install -r requirements.txt
# Set your Gemini API Key
export GEMINI_API_KEY="your_api_key_here"
# Run Server
python -m uvicorn main:app --reload
```

### Frontend Setup

```bash
cd app/frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to start translating papers.

## Testing

Run the full test suite from the project root:

```bash
# Backend Tests
python -m pytest app/backend/tests

# E2E Tests
python tests/test_e2e_2510_26692.py
```

## License

Apache-2.0
