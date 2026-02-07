# ReadPaper Frontend

The frontend application for ReadPaper, built with **Next.js 14**, **Tailwind CSS**, and **React**. It provides a responsive interface for inputting arXiv URLs and viewing papers in a split-view layout.

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **PDF Rendering**: Native `<iframe>` embedding (MVP)

## Key Components

- `app/page.tsx`: Main entry point handling URL input and state management.
- `components/SplitView.tsx`: The core reading interface displaying Original and Translated PDFs side-by-side.
- `components/ui`: Reusable UI components (Buttons, Inputs, Progress Bars).

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

- `NEXT_PUBLIC_API_URL`: URL of the backend API (default: `http://localhost:8000`).
