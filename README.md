

<div align="center">
  <img src="logo.svg" width="120" alt="ReadPaper Logo" />
  <h1>ReadPaper: Bilingual AI ArXiv Reader</h1>
  <p><strong>Powered by Gemini 3.0 Flash</strong></p>
</div>

![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js](https://img.shields.io/badge/next.js-14+-black.svg)
![GCP](https://img.shields.io/badge/Google_Cloud-Ready-4285F4.svg)
![Model](https://img.shields.io/badge/Gemini-3.0_Flash-blue?logo=google)

**ReadPaper** is an open-source tool that translates arXiv papers from English to Chinese while **preserving the original LaTeX layout**, equations, citations, figures, and tables. It leverages **Gemini 3.0 Flash** with its 1M context window for whole-file translation.

> [!IMPORTANT]
> This project uses **Gemini 3.0 Flash** (`gemini-3-flash-preview`) exclusively. Each `.tex` file is translated in a single API call — no chunking, no batching, no text-node extraction.

## 🚀 Key Features

- **Whole-File Translation**: Each `.tex` file is sent to Gemini as-is (complete LaTeX source), translated to Chinese in one API call. No text extraction, no batching, no reassembly corruption.
- **CJK-Ready Output**: Translation prompt instructs Gemini to add `\usepackage[UTF8]{ctex}` and preserve all LaTeX commands.
- **Smart Structure Analysis** (`analyzer.py`): Classifies files as main/sub/macro/style, builds `\input` dependency graph, identifies the main `.tex` entrypoint.
- **AI Compile Fix Loop** (`compiler.py`): Up to 3 iterative compile attempts with Gemini-powered error fixing. Parses error log → fixes the offending file → retries.
- **Dynamic Compile Timeout**: Base 300s + 60s per 10k output tokens, capped at 1200s. Adapts to paper size automatically.
- **Translation Cache**: GCS-backed cache with integrity validation — previously translated papers are served instantly.
- **Token Usage Tracking**: Real-time Gemini API token usage displayed in frontend during translation.
- **Admin Dashboard**: Full admin panel with user management, paper management (delete), and system overview.
- **GCS Signed URL Delivery**: PDFs served via time-limited signed URLs directly from GCS — no backend proxy bottleneck.
- **Cloud Scale**: Google Cloud Run with `--no-cpu-throttling` for reliable background task execution + GCS storage.
- **Split-View Reader**: Side-by-side bilingual PDF viewing in Next.js frontend.
- **Google OAuth**: Secure authentication via Google Sign-In with per-user paper libraries.

## 🏗️ Architecture

```
User → Next.js Frontend → FastAPI Backend
                                ↓
                    ┌─── Translation Pipeline ──────────────────┐
                    │                                            │
                    │  Step 1: Download + Extract Source          │
                    │     └─ arXiv e-print → tar.gz → workspace │
                    │                                            │
                    │  Step 2: PaperAnalyzer                     │
                    │     └─ Classify files, find main .tex      │
                    │                                            │
                    │  Step 3: Whole-File Translation             │
                    │     └─ Each .tex → Gemini API → Chinese    │
                    │     └─ asyncio.gather() for concurrency    │
                    │                                            │
                    │  Step 4: Compile + AI Fix Loop              │
                    │     └─ latexmk -xelatex (up to 3 tries)   │
                    │     └─ Gemini fixes errors between retries │
                    └────────────────────────────────────────────┘
                                ↓
                     GCS / Local Storage → Signed URL → Browser
```

## 🧠 How Translation Works

### Whole-File Approach

Each `.tex` file is translated in a **single Gemini API call** with the full file content as input. The prompt instructs the model to:
1. Translate all human-readable English text to Chinese
2. Preserve all LaTeX commands, environments, labels, citations, and math exactly
3. Add `\usepackage[UTF8]{ctex}` to the main document if not present
4. Keep the file structure byte-compatible (same number of environments, same nesting)

This avoids all the problems of text extraction + reassembly: no offset drift, no broken environments, no missing citations.

### Concurrency

Translation uses `asyncio.gather()` with a `Semaphore` to process multiple `.tex` files in parallel (default concurrency: 4). Files are translated independently, then the whole project is compiled as a unit.

### Compile + AI Fix Loop

After translation, the project is compiled with `latexmk -xelatex`:
1. On failure, the error log is parsed to identify the failing file and error type
2. Gemini is asked to fix the specific file
3. Compilation is retried (up to 3 attempts)

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Gemini API key from [AI Studio](https://aistudio.google.com/) |
| `STORAGE_TYPE` | No | `local` (default) or `gcs` |
| `GCS_BUCKET_NAME` | For GCS | GCS bucket name |
| `GOOGLE_CLIENT_ID` | For auth | Google OAuth 2.0 Client ID |
| `MAX_CONCURRENT_REQUESTS` | No | Concurrent Gemini API calls (default: 4) |
| `DISABLE_AUTH` | No | Set `true` for local dev (skips OAuth) |

### Local Development

```bash
cp .env.example .env
# Set GEMINI_API_KEY and DISABLE_AUTH=true
./run_conda_local.sh
```

### Cloud Deployment

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_GEMINI_API_KEY=...,_GOOGLE_CLIENT_ID=...,_GOOGLE_CLIENT_SECRET=...,_NEXTAUTH_SECRET=...
```

Cloud Run backend is configured with:
- `--cpu=2` — Sufficient CPU for LaTeX compilation
- `--timeout=900` — 15-minute request timeout for long compilations
- `--no-cpu-throttling` — Background tasks (compilation) get full CPU even after request returns

## 📦 Project Structure

```
├── app/
│   ├── backend/
│   │   ├── arxiv_translator/       # Core translation pipeline
│   │   │   ├── main.py             # Pipeline orchestrator (CLI entry point)
│   │   │   ├── translator.py       # Gemini whole-file translation
│   │   │   ├── analyzer.py         # File classification & dependency graph
│   │   │   ├── compiler.py         # Compile + AI error-fix loop
│   │   │   ├── downloader.py       # arXiv source download + extraction
│   │   │   ├── latex_cleaner.py    # Pre-translation LaTeX cleanup
│   │   │   ├── logging_utils.py    # Structured logging
│   │   │   └── prompts/
│   │   │       ├── whole_file_translation_prompt.txt
│   │   │       └── latex_fix_prompt.txt
│   │   ├── services/
│   │   │   ├── auth.py             # Google OAuth verification
│   │   │   ├── storage.py          # Local / GCS storage abstraction
│   │   │   ├── library.py          # User paper library (GCS-backed)
│   │   │   ├── cache.py            # Translation cache with integrity checks
│   │   │   └── rate_limiter.py     # API rate limiting
│   │   ├── main.py                 # FastAPI REST API + admin endpoints
│   │   └── Dockerfile
│   ├── frontend/
│   │   ├── components/
│   │   │   ├── ClientHome.tsx      # Main UI with progress + token display
│   │   │   └── SplitView.tsx       # Split-view PDF reader
│   │   ├── app/
│   │   │   ├── admin/page.tsx      # Admin dashboard
│   │   │   └── api/backend/        # Backend proxy with streaming
│   │   └── Dockerfile
├── tests/
│   └── test_e2e_pipeline.py        # Mocked E2E test
├── cloudbuild.yaml                 # Full stack CI/CD
└── cloudbuild-hotfix.yaml          # Backend-only hotfix deploy
```

## 📊 Token Usage

ReadPaper tracks and displays Gemini API token usage in real-time:
- **During translation**: Live token counter shown next to elapsed timer
- **Per-file tracking**: Each file's input/output tokens are reported via IPC
- **Final summary**: Total tokens displayed when translation completes

Hover the token counter for a breakdown of input vs output tokens.

## 🤝 Contributing

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'feat: description'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## 📄 License

Distributed under the Apache-2.0 License. See `LICENSE` for more information.
