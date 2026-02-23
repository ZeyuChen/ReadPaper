
<div align="center">
  <img src="logo.svg" width="120" alt="ReadPaper Logo" />
  <h1>ReadPaper</h1>
  <p><strong>AI-powered bilingual arXiv reader — translate any paper to Chinese with one click</strong></p>
  <p>
    <a href="https://readpaper-frontend-989182646968.us-central1.run.app">Live Demo</a> ·
    <a href="#-quick-start">Quick Start</a> ·
    <a href="ARCHITECTURE.md">Architecture</a>
  </p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Gemini_3.0_Flash-1M_context-4285F4?logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js_14-black?logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/Google_Cloud-Run-4285F4?logo=googlecloud&logoColor=white" />
  <img src="https://img.shields.io/badge/license-Apache_2.0-blue" />
</p>

---

ReadPaper downloads an arXiv paper's LaTeX source, translates every `.tex` file to Chinese **in a single Gemini API call** per file, recompiles with XeLaTeX, and presents the result in a side-by-side split-view reader. No text extraction, no chunking, no layout corruption.

## ✨ Why ReadPaper?

| Problem | ReadPaper's Approach |
|---------|---------------------|
| PDF translators break equations and formatting | Translates **raw LaTeX source** — math, citations, figures stay pixel-perfect |
| Chunk-based approaches corrupt cross-references | **Whole-file translation** — each `.tex` file sent as-is in one API call |
| Compilation errors after translation | **AI-powered fix loop** — Gemini auto-fixes LaTeX errors, retries up to 3× |
| Slow PDF delivery through backend proxies | **GCS signed URLs** — browser downloads directly from storage (1 hop) |

## 🚀 Quick Start

### Local Development

```bash
git clone https://github.com/ZeyuChen/ReadPaper.git && cd ReadPaper
cp .env.example .env  # Set GEMINI_API_KEY, DISABLE_AUTH=true
./run_conda_local.sh
```

### Cloud Deployment (Google Cloud)

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions="_GEMINI_API_KEY=...,_GOOGLE_CLIENT_ID=...,_GOOGLE_CLIENT_SECRET=...,_NEXTAUTH_SECRET=..."
```

## 🏗️ How It Works

```
 ┌─────────────┐    ┌──────────────────────────────────────────────┐
 │  Next.js UI  │───▶│              FastAPI Backend                  │
 │  Split View  │◀───│                                              │
 │  + OAuth     │    │  1. Download arXiv source (.tar.gz)          │
 └─────────────┘    │  2. PaperAnalyzer: classify .tex files       │
        │           │  3. Gemini 3.0 Flash: translate each file    │
        │           │  4. XeLaTeX compile + AI error fix loop      │
        ▼           │  5. Upload PDF to GCS                        │
 ┌─────────────┐    └──────────────────────────────────────────────┘
 │  GCS Signed  │◀── Cached signed URLs (12-min TTL)
 │  URL (1 hop) │    No backend proxy for PDF delivery
 └─────────────┘
```

### Translation Pipeline

1. **Download** — fetch arXiv e-print tarball, extract source files
2. **Analyze** — `PaperAnalyzer` classifies files (main/sub/macro/style/bib), builds `\input` dependency graph
3. **Translate** — each translatable `.tex` file → Gemini 3.0 Flash in one API call, `asyncio.gather()` with semaphore (4 concurrent)
4. **Compile** — `latexmk -xelatex` with dynamic timeout (300–1200s based on token count)
5. **Fix Loop** — on compile failure, Gemini reads the error log and fixes the offending file (up to 3 retries)

### What Gets Preserved

| Translated | Untouched |
|-----------|-----------|
| Prose, section titles, captions, abstract | `\cite{}`, `\ref{}`, `\label{}` |
| English comments | All math: `$...$`, `\begin{equation}` |
| Footnotes, acknowledgments | Package imports, macros, BibTeX |

## 📦 Project Structure

```
app/
├── backend/
│   ├── main.py                    # FastAPI API (1285 lines) — translate, status, PDF delivery, admin
│   ├── arxiv_translator/
│   │   ├── analyzer.py            # .tex file classifier + dependency graph
│   │   ├── translator.py          # Gemini whole-file translation with retry
│   │   ├── compiler.py            # XeLaTeX compile + AI error fix loop
│   │   ├── downloader.py          # arXiv source download + extraction
│   │   ├── latex_cleaner.py       # Pre-translation comment cleanup
│   │   └── prompts/               # Translation & fix prompt templates
│   └── services/
│       ├── storage.py             # Local / GCS storage abstraction
│       ├── cache.py               # Translation cache with integrity validation
│       ├── auth.py                # Google OAuth token verification
│       ├── library.py             # Per-user paper library (GCS-backed)
│       └── rate_limiter.py        # API rate limiting
├── frontend/
│   ├── components/
│   │   ├── SplitView.tsx          # Side-by-side PDF reader with zoom & notes
│   │   └── ClientHome.tsx         # Main UI — paper library, translate, progress
│   ├── app/
│   │   ├── admin/page.tsx         # Admin dashboard — users, papers, analytics
│   │   └── api/backend/           # Proxy with binary streaming support
│   ├── auth.ts                    # NextAuth.js Google OAuth config
│   └── middleware.ts              # Auth middleware for route protection
cloudbuild.yaml                    # Full-stack CI/CD (frontend + backend)
cloudbuild-hotfix.yaml             # Backend-only rapid deploy
```

## ⚙️ Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ | From [Google AI Studio](https://aistudio.google.com/) |
| `GOOGLE_CLIENT_ID` | For auth | Google OAuth 2.0 Web Client ID |
| `GOOGLE_CLIENT_SECRET` | For auth | OAuth client secret |
| `NEXTAUTH_SECRET` | For auth | NextAuth.js session secret |
| `STORAGE_TYPE` | No | `local` (default) or `gcs` |
| `GCS_BUCKET_NAME` | For GCS | Google Cloud Storage bucket |
| `DISABLE_AUTH` | No | `true` for local dev (bypasses OAuth) |
| `MAX_CONCURRENT_REQUESTS` | No | Parallel Gemini API calls (default: 4) |

## 🔧 Cloud Run Settings

| Setting | Value | Why |
|---------|-------|-----|
| `--cpu 2` | 2 vCPU | XeLaTeX compilation is CPU-intensive |
| `--memory 4Gi` | 4 GB | Large papers need memory for TeX processing |
| `--timeout 900` | 15 min | Long papers with many files need time |
| `--no-cpu-throttling` | ✔ | Background compilation gets full CPU after response |
| `--min-instances 1` | 1 | Avoid cold starts |

## 📊 Features at a Glance

- **🔐 Google OAuth** — secure per-user paper libraries
- **📊 Admin Dashboard** — user management, paper management, system overview
- **⚡ Signed URL PDF Delivery** — cached GCS signed URLs, 12-min TTL, zero backend proxy
- **📈 Live Token Tracking** — real-time Gemini API token usage during translation
- **💾 Translation Cache** — GCS-backed with integrity checks, skip re-translation
- **🔄 AI Compile Fix Loop** — Gemini reads LaTeX errors and auto-fixes (3 retries)
- **📝 Reading Notes** — per-paper notes saved in browser localStorage
- **⌨️ Keyboard Shortcuts** — zoom (⌘+/-), toggle notes (N), toggle sidebar (S)

## 🤝 Contributing

1. Fork → `git checkout -b feature/my-feature`
2. Commit → `git push origin feature/my-feature`
3. Open a Pull Request

**Requirements**: Python 3.11+, Node.js 18+, TeX Live (with `latexmk`, `xelatex`, `fandol` fonts)

## 📄 License

Apache-2.0 · See [LICENSE](LICENSE)
