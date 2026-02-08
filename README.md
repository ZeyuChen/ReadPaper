
# ReadPaper: Bilingual AI ArXiv Reader

![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js](https://img.shields.io/badge/next.js-14+-black.svg)
![GCP](https://img.shields.io/badge/Google_Cloud-Ready-4285F4.svg)

**ReadPaper** automates the translation of technical arXiv papers from English to Chinese (and other languages) while preserving the original LaTeX layout and formatting. It leverages **Gemini 3.0 Flash/Pro** for high-fidelity translation and **DeepDive** AI analysis to inject expert insights directly into the document.

The project is designed for cloud-native deployment on **Google Cloud Run**, utilizing **Cloud Storage (GCS)** for artifact management.

## 🚀 Features

- **LaTeX-Native Translation**: Translates source code directly to preserve complex equations, tables, and citations.
- **DeepDive Analysis (New)**: Performs an initial AI pass to generate English-language insights, which are then translated and embedded into the final PDF.
- **Split-View Interface**: Modern Next.js frontend for side-by-side reading of original and translated versions.
- **Cloud Scale**: Built on Google Cloud Run for serverless scalability.
- **Robust Compilation**: Dockerized TeX Live environment ensures consistent PDF generation.

## 🏗️ Architecture

```mermaid
graph TD
    User[User] -->|Upload/Url| FE[Frontend (Next.js)]
    FE -->|API Request| BE[Backend (FastAPI)]
    
    subgraph Google Cloud Platform
        BE -->|Download Src| ArXiv[arXiv.org]
        BE -->|Analysis & Translation| Gemini[Gemini 1.5/3.0 API]
        BE -->|Store Artifacts| GCS[Google Cloud Storage]
        BE -->|Compile PDF| Tex[TeX Live Engine]
    end
    
    GCS -->|Serve PDFs| FE
```

## 🛠️ Deployment on Google Cloud

This repository is configured for automated deployment via **Google Cloud Build**.

### Prerequisites

1.  **Google Cloud Project** with billing enabled.
2.  **APIs Enabled**: Cloud Run, Cloud Build, Artifact Registry, Cloud Storage.
3.  **Encrypted Secrets**: Store your `GEMINI_API_KEY` in Google Secret Manager.

### One-Click Deploy (Manual)

Refer to [deployment.md](./deployment.md) for a step-by-step guide on deploying from your local machine using the `gcloud` CLI.

### CI/CD with Cloud Build

The included `cloudbuild.yaml` automated the build and deploy process on every push to the `main` branch.

1.  Connect your GitHub repository to Cloud Build.
2.  Set the following Substitution Variables in Cloud Build trigger:
    -   `_REGION`: Your preferred region (e.g., `us-central1`).
    -   `_BUCKET_NAME`: Your GCS bucket name.
    -   `_GEMINI_API_KEY`: (Or mount from Secret Manager).

## 📦 Project Structure

```
├── app/
│   ├── backend/          # FastAPI Service (Python 3.11)
│   │   ├── Dockerfile    # Full TeX Live environment
│   │   └── ...
│   ├── frontend/         # Next.js Application
│   │   ├── Dockerfile    # Standalone output build
│   │   └── ...
├── arxiv-translator/     # Core Translation Logic
├── cloudbuild.yaml       # CI/CD Configuration
└── deployment.md         # Manual Deployment Guide
```

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

## 📄 License

Apache-2.0
