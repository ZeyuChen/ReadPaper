

<div align="center">
  <img src="logo.svg" width="120" alt="ReadPaper Logo" />
  <h1>ReadPaper: Bilingual AI ArXiv Reader</h1>
</div>

![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js](https://img.shields.io/badge/next.js-14+-black.svg)
![GCP](https://img.shields.io/badge/Google_Cloud-Ready-4285F4.svg)

**ReadPaper** is an open-source tool that revolutionizes how you read academic papers. It automates the translation of technical arXiv papers from English to Chinese while **preserving the original LaTeX layout**, citations, equations, and bibliography references.

It leverages **Gemini 2.0 Flash** for high-fidelity translation and the optional **AI DeepDive** feature to inject expert insights directly into the document, creating a truly bilingual reading experience.

The project is designed for cloud-native deployment on **Google Cloud Run**, utilizing **Cloud Storage (GCS)** for scalable artifact management.

## 🚀 Key Features

- **Text-Node Translation (v2)**: The LLM only ever sees pure English prose — never raw LaTeX commands. This eliminates structural corruption and citation loss.
- **Citation & Bibliography Preservation**: The entire `\begin{thebibliography}` section, `.bib` files, and all `\cite{}`, `\ref{}`, `\label{}` commands are always skipped — references remain untouched.
- **AI DeepDive Analysis**: Injects styled explanation boxes (blue-bordered, small font) directly into the PDF after dense technical paragraphs for guided reading.
- **4-Phase Robust Pipeline**:
  1. **Structural Analysis** (`analyzer.py`) — classifies files, builds `\input` dependency graph, identifies the main `.tex` entrypoint recursively.
  2. **Text-Node Extraction + Translation** (`text_extractor.py` + `translator.py`) — extracts pure prose spans using a state-machine; LLM receives only human-readable text. Macro/style/bibliography files are never translated.
  3. **Post-Processing** (`post_process.py`) — injects `ctex`, `xcolor` packages; renames conflicting macros; deduplicates labels cross-file.
  4. **Compile + AI Fix Loop** (`compiler.py`) — up to 3 iterative compile attempts; each failure triggers targeted AI repair of the failing file before retrying.
- **Partial Translation Warnings**: When API failures leave text in English, a warning comment is injected into the source and the frontend progress bar shows a yellow indicator.
- **Split-View Interface**: Next.js frontend for side-by-side bilingual reading.
- **Cloud Scale**: Google Cloud Run + GCS with direct blob streaming (no signed-URL dependency).
- **Local Ready**: `run_conda_local.sh` or `docker-compose` for local development.

## ⚙️ Dual-Mode Configuration

A template is provided in `.env.example`.

### Mode 1: Local Development

```bash
cp .env.example .env
# Set:
#   GEMINI_API_KEY=<your key>
#   STORAGE_TYPE=local        # saves to ./paper_storage
#   DISABLE_AUTH=true         # skips Google Login
```

### Mode 2: Cloud Deployment (Google Cloud Run)

```bash
# Required Cloud Run env vars:
#   STORAGE_TYPE=gcs
#   GCS_BUCKET_NAME=<your bucket>
#   GEMINI_API_KEY=<your key>
#   GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET  (OAuth)
#   NEXTAUTH_SECRET   (frontend)
```

## 🏗️ Architecture

```
User → Next.js Frontend → FastAPI Backend
                                ↓
                    ┌─── Translation Pipeline ───────────────────────┐
                    │                                                   │
                    │  Phase 0: PaperAnalyzer                          │
                    │     └─ Classify files (main/sub/macro/style)     │
                    │                                                   │
                    │  Phase 1+2: Text-Node Translation                │
                    │     ├─ LatexTextExtractor: extract prose spans   │
                    │     ├─ GeminiTranslator:   translate prose only  │
                    │     └─ Reintegrate at original char offsets      │
                    │                                                   │
                    │  Phase 3 (optional): AI DeepDive                 │
                    │     └─ Inject styled explanation boxes           │
                    │                                                   │
                    │  Phase 4: Post-Process → Compile + Fix Loop      │
                    │     ├─ Inject ctex, xcolor packages              │
                    │     └─ Up to 3 AI-driven compile fix attempts    │
                    └───────────────────────────────────────────────────┘
                                ↓
                     GCS / Local Storage → PDF served via StreamingResponse
```

## 🧠 Translation Pipeline — Deep Dive

### Why Text-Node Translation?

Previous approaches sent raw LaTeX to the LLM, which frequently:
- Corrupted `\begin{...}` / `\end{...}` structure
- Changed citation keys inside `\cite{}`
- Translated bibliography entries (breaking reference formatting)

**The text-node approach** extracts only pure English prose segments (skipping all math, commands, environments, preamble, and bibliography blocks) and sends those to the LLM. The LLM never sees LaTeX structure, so structural corruption is **impossible by design**.

### What Is Never Translated

| Skipped Content | Why |
|---|---|
| `\begin{thebibliography}...\end{thebibliography}` | Entire references section preserved |
| `.bib` files | Only formatting fixes applied |
| `\cite{}`, `\ref{}`, `\label{}`, `\eqref{}` | Keys must stay intact |
| Preamble (before `\begin{document}`) | Package options must not change |
| Math (`$...$`, `\begin{equation}`, ...) | Formulas must stay in English |
| Macro / style / standalone files | Classified and skipped by PaperAnalyzer |
| `\begin{algorithm}`, `\begin{verbatim}`, ... | Code/pseudocode stays literal |

### Failure Handling

If Gemini API calls fail (network/quota), the affected text nodes fall back to **original English**. The pipeline:
1. Injects a `% ⚠ TRANSLATION WARNING: N segment(s)...` comment in the LaTeX source
2. Emits `PROGRESS:WARN:...` to the progress stream — frontend shows a yellow indicator
3. Emits `PROGRESS:COMPLETED_WITH_WARNINGS:...` at completion instead of the normal green

### AI DeepDive

Styled explanation block injected after dense paragraphs:
```latex
{\par\smallskip\noindent\fbox{\begin{minipage}{0.93\linewidth}
\textcolor{blue!70!black}{\small\textbf{[AI DeepDive] Concept}}\\
\textcolor{blue!50!black}{\small\textbf{解释：} explanation in Chinese}\\
\textcolor{blue!50!black}{\small\textit{为什么重要：} why it matters}
\end{minipage}}\par\smallskip}
```
Uses only `xcolor` (always injected) — no `tcolorbox` dependency to avoid package clashes.

## 📋 Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **TeX Live** (with `latexmk`, `xelatex`, `fandol` fonts) — or Docker (used as fallback)
- **Google Cloud SDK** (for GCP deployment)
- **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

## 🛠️ Usage

### CLI Translation

```bash
# Basic translation
python -m app.backend.arxiv_translator.main https://arxiv.org/abs/2502.12345

# With AI DeepDive analysis
python -m app.backend.arxiv_translator.main https://arxiv.org/abs/2502.12345 --deepdive

# Use a specific model
python -m app.backend.arxiv_translator.main 2502.12345 --model gemini-2.0-pro
```

### Web Interface

1. Navigate to the web UI and sign in.
2. Enter an arXiv URL or ID in the search box.
3. Optionally enable **DeepDive Analysis**.
4. Click **Translate** and monitor the live progress bar.
5. Once complete, the Split-View reader opens automatically.

## 🛠️ Deployment

### Local Deployment

```bash
./run_conda_local.sh        # starts backend + frontend locally
```

See [deployment.md](./deployment.md) for detailed steps.

### Cloud Build (CI/CD)

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_GEMINI_API_KEY=...,_GOOGLE_CLIENT_ID=...,_GOOGLE_CLIENT_SECRET=...
```

The `cloudbuild.yaml` builds both Docker images, pushes to Artifact Registry, and deploys to Cloud Run.

## 📦 Project Structure

```
├── app/
│   ├── backend/
│   │   ├── arxiv_translator/       # Core 4-phase translation pipeline
│   │   │   ├── analyzer.py         # Phase 0: file classification & dependency graph
│   │   │   ├── text_extractor.py   # Phase 1: prose text-node extraction (FSM)
│   │   │   ├── translator.py       # Phase 2: Gemini text-node translation
│   │   │   ├── deepdive.py         # Phase 2b (optional): AI insight injection
│   │   │   ├── post_process.py     # Phase 3: ctex/xcolor injection & label fixes
│   │   │   ├── compiler.py         # Phase 4: compile + AI error-fix loop
│   │   │   ├── main.py             # Pipeline orchestrator (CLI entry point)
│   │   │   ├── extractor.py        # Source archive extraction
│   │   │   ├── downloader.py       # arXiv source download
│   │   │   ├── latex_rescuer.py    # Last-resort rescue compilation
│   │   │   └── prompts/            # LLM prompt templates
│   │   ├── services/
│   │   │   ├── auth.py             # Google OAuth token verification
│   │   │   ├── storage.py          # LocalStorage / GCS storage abstraction
│   │   │   └── library.py          # User paper library management
│   │   ├── main.py                 # FastAPI app: REST endpoints + IPC stream handler
│   │   └── Dockerfile
│   ├── frontend/
│   │   └── Dockerfile
├── cloudbuild.yaml
└── deployment.md
```

## 🤝 Contributing

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'feat: description'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## 📄 License

Distributed under the Apache-2.0 License. See `LICENSE` for more information.
