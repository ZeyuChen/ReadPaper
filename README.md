

<div align="center">
  <img src="logo.svg" width="120" alt="ReadPaper Logo" />
  <h1>ReadPaper: Bilingual AI ArXiv Reader</h1>
</div>

![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js](https://img.shields.io/badge/next.js-14+-black.svg)
![GCP](https://img.shields.io/badge/Google_Cloud-Ready-4285F4.svg)

**ReadPaper** is an open-source tool that revolutionizes how you read academic papers. It automates the translation of technical arXiv papers from English to Chinese (and other languages) while **preserving the original LaTeX layout**, citations, and mathematical formulas. 

It leverages **Gemini 3.0 Flash/Pro** for high-fidelity translation and **DeepDive** AI analysis to inject expert insights directly into the document, creating a truly bilingual reading experience.

The project is designed for cloud-native deployment on **Google Cloud Run**, utilizing **Cloud Storage (GCS)** for scalable artifact management.

## 🚀 Key Features

- **LaTeX-Native Translation**: Translates source code directly to preserve complex equations, tables, and citations.
- **DeepDive Analysis (New)**: Performs an initial AI pass to generate English-language insights for complex technical concepts, which are then translated and embedded into the final PDF.
- **AI-Powered Recovery (New)**: Automatically detects PDF compilation failures and uses Gemini 3.0 Flash to "fix" broken LaTeX code, ensuring a robust output even with malformed inputs.
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

## 🧠 DeepDive Analysis

The **DeepDive** feature enhances the reading experience by injecting AI-generated insights directly into the paper.

1.  **Analysis**: The system analyzes the abstract and introduction to generate a high-level summary and identify key technical concepts.
2.  **Insight Generation**: Gemini generates "Insight Cards" for complex terms or equations.
3.  **Injection**: These insights are translated and embedded into the final LaTeX source as side notes or margin comments before compilation, appearing natively in the translated PDF.

## 📋 Prerequisites

Before running the project locally, ensure you have the following installed:

-   **Python 3.11+**: For the backend service and translation logic.
-   **Node.js 18+**: For the Next.js frontend.
-   **Docker**: Required for the backend if you want to ensure a consistent TeX Live environment.
-   **Google Cloud SDK**: For deploying to Cloud Run (optional for local dev).
-   **Gemini API Key**: Get one from [Google AI Studio](https://aistudio.google.com/).

## 🛠️ Usage

### CLI Translation

To translate a paper with DeepDive enabled:

```bash
# Basic Translation
python -m app.backend.arxiv_translator.main https://arxiv.org/abs/2502.12345

# With DeepDive (Technical Analysis)
python -m app.backend.arxiv_translator.main https://arxiv.org/abs/2502.12345 --deepdive
```

### Web Interface

1.  Navigate to the web UI.
2.  Enter the arXiv URL or ID.
3.  Toggle the **"Enable DeepDive Analysis"** switch.
4.  Click **Translate**.

## 🛠️ Deployment


This repository is configured for automated deployment via **Google Cloud Build**.

### Local Deployment (Manual)

Refer to [deployment.md](./deployment.md) for a step-by-step guide on deploying from your local machine using the `gcloud` CLI.

### CI/CD with Cloud Build

The included `cloudbuild.yaml` automates the build and deploy process on every push to the `main` branch.

1.  Connect your GitHub repository to Cloud Build.
2.  Set the following Substitution Variables in Cloud Build trigger:
    -   `_REGION`: Your preferred region (e.g., `us-central1`).
    -   `_BUCKET_NAME`: Your GCS bucket name.
    -   `_GEMINI_API_KEY`: (Or mount from Secret Manager).

## 📦 Project Structure

```
├── app/
│   ├── backend/          # FastAPI Service (Python 3.11)
│   │   ├── arxiv_translator/ # Core Translation Logic & DeepDive
│   │   ├── services/     # Auth, Library, and Storage Services
│   │   ├── Dockerfile    # Full TeX Live environment
│   │   └── ...
│   ├── frontend/         # Next.js Application
│   │   ├── Dockerfile    # Standalone output build
│   │   └── ...
├── cloudbuild.yaml       # CI/CD Configuration
└── deployment.md         # Manual Deployment Guide
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1.  Fork the repo
2.  Create your feature branch (`git checkout -b feature/amazing-feature`)
3.  Commit your changes (`git commit -m 'Add some amazing feature'`)
4.  Push to the branch (`git push origin feature/amazing-feature`)
5.  Open a Pull Request

## 📄 License

Distributed under the Apache-2.0 License. See `LICENSE` for more information.
