# ReadPaper Frontend

The frontend application for ReadPaper, built with **Next.js 14**, **Tailwind CSS**, and **React**. It provides a responsive interface for inputting arXiv URLs and viewing papers in a split-view layout.

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **Authentication**: NextAuth.js (v5 Beta) with Google Provider
- **Icons**: Lucide React & React Icons
- **PDF Rendering**: Native `<iframe>` embedding with authenticated fetching

## 🔐 Authentication

The app uses **NextAuth.js** for secure Google Sign-In.

1.  Set up OAuth credentials in the [Google Cloud Console](https://console.cloud.google.com/).
2.  Add the Client ID and Secret to your `.env` file:
    ```bash
    AUTH_GOOGLE_ID=your_client_id
    AUTH_GOOGLE_SECRET=your_client_secret
    AUTH_SECRET=your_random_secret_string
    ```

## Key Components

- **`app/page.tsx`**: Main entry point handling URL input and state management.
- **`app/login/page.tsx`**: Custom login page designed to match Google's aesthetic.
- **`components/SplitView.tsx`**: The core reading interface. It manages side-by-side PDF viewing and fetches protected PDF content using the session's ID token.
- **`components/ClientHome.tsx`**: The main dashboard showing the search bar and the user's paper library.

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
