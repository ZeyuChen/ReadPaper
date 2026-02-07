'use client';

import { useState, useEffect } from 'react';
import SplitView from '@/components/SplitView';
import { Search, Loader2 } from 'lucide-react';

export default function Home() {
  const [url, setUrl] = useState('');
  // const [model, setModel] = useState('flash'); // Removed, default to flash
  const [arxivId, setArxivId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [progress, setProgress] = useState(0);
  const [library, setLibrary] = useState([]);

  useEffect(() => {
    fetchLibrary();
  }, [arxivId]); // Reload when returning from split view

  const fetchLibrary = async () => {
    try {
      const res = await fetch('http://localhost:8000/library');
      if (res.ok) {
        const data = await res.json();
        setLibrary(data);
      }
    } catch (e) {
      console.error("Failed to fetch library", e);
    }
  };

  const handleTranslate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setStatusMessage('');

    // Simple verification
    if (!url.includes('arxiv.org')) {
      setError('Please enter a valid arXiv URL');
      return;
    }

    setLoading(true);
    setStatusMessage('Initializing translation...');

    try {
      // Extract ID for optimistic UI update (real app should wait for ack)
      // Supported formats: https://arxiv.org/abs/2401.00001 or https://arxiv.org/pdf/2401.00001.pdf
      const matches = url.match(/(\d{4}\.\d{4,5})/);
      const extractedId = matches ? matches[1] : null;

      if (!extractedId) {
        throw new Error("Could not extract arXiv ID");
      }

      // Call Backend
      const response = await fetch('http://localhost:8000/translate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ arxiv_url: url, model: 'flash' }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        if (errData.status === 'completed' || errData.message === 'Already completed') {
          setArxivId(extractedId);
          setLoading(false);
          return;
        }
        throw new Error(errData.detail || 'Translation request failed');
      }

      // Poll STATUS
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch(`http://localhost:8000/status/${extractedId}`);
          const statusData = await statusRes.json();
          console.log("Status:", statusData.status);

          if (statusData.message) {
            setStatusMessage(statusData.message);
          }
          if (statusData.progress) {
            setProgress(statusData.progress);
          }

          if (statusData.status === 'completed') {
            clearInterval(pollInterval);
            setArxivId(extractedId);
            setLoading(false);
            setStatusMessage('');
            setProgress(0);
          } else if (statusData.status === 'failed') {
            clearInterval(pollInterval);
            setError(`Translation failed: ${statusData.message || 'Unknown error'}`);
            setLoading(false);
            setStatusMessage('');
            setProgress(0);
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 1000);

    } catch (err: any) {
      setError(err.message || 'An error occurred');
      setLoading(false);
      setStatusMessage('');
    }
  };

  if (arxivId) {
    return (
      <SplitView
        arxivId={arxivId}
        onPaperSelect={setArxivId}
        onBack={() => setArxivId(null)}
      />
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 bg-gradient-to-br from-gray-50 to-blue-50">
      <div className="w-full max-w-3xl space-y-8 text-center">
        <div className="space-y-2">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
            ReadPaper
          </h1>
          <p className="text-lg text-gray-600">
            Bilingual arXiv reading experience powered by Gemini 3.0
          </p>
        </div>

        <form onSubmit={handleTranslate} className="relative group flex gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none text-gray-400">
              <Search size={20} />
            </div>
            <input
              type="text"
              placeholder="Paste arXiv URL (e.g., https://arxiv.org/abs/2602.04705)"
              className="w-full py-4 pl-12 pr-4 text-gray-900 bg-white border border-gray-200 rounded-xl shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition-all text-lg"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={loading}
            />
          </div>

          {/* Model selection removed as per requirement: default to Flash */}

          <button
            type="submit"
            disabled={loading || !url}
            className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-4 rounded-xl transition-colors flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed shadow-sm min-w-[120px]"
          >
            {loading ? <Loader2 className="animate-spin" /> : 'Read'}
          </button>
        </form>

        {loading && (
          <div className="w-full max-w-md mx-auto space-y-2">
            <div className="flex justify-between text-xs text-blue-600 font-medium px-1">
              <span>{statusMessage || 'Initializing...'}</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 w-full bg-blue-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 transition-all duration-500 ease-out rounded-full"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 mb-4 text-red-700 bg-red-100 rounded-lg border border-red-200">
            {error}
          </div>
        )}
      </div>

      {/* Library Section */}
      <div className="w-full max-w-4xl px-4 py-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center gap-2">
          My Library <span className="text-sm font-normal text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">{library.length}</span>
        </h2>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2">
          {library.map((paper: any) => (
            <div
              key={paper.id}
              onClick={() => setArxivId(paper.id)}
              className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 hover:shadow-md hover:border-blue-200 transition cursor-pointer group flex flex-col h-full"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{paper.id}</span>
                <span className="text-xs text-gray-400">{new Date(paper.added_at).toLocaleDateString()}</span>
              </div>

              <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-700 transition line-clamp-2 mb-2">
                {paper.title || `arXiv:${paper.id}`}
              </h3>

              {/* Tags */}
              <div className="flex flex-wrap gap-1 mb-3">
                {(paper.categories || []).slice(0, 3).map((tag: string) => (
                  <span key={tag} className="text-[10px] text-gray-500 border px-1.5 py-0.5 rounded bg-gray-50">
                    {tag}
                  </span>
                ))}
              </div>

              <p className="text-sm text-gray-600 line-clamp-3 mb-4 flex-1">
                {paper.abstract || "No abstract available."}
              </p>

              <div className="flex items-center gap-1 text-xs text-gray-400 mt-auto pt-3 border-t">
                <span className="truncate max-w-full">
                  {(paper.authors || []).join(", ")}
                </span>
              </div>
            </div>
          ))}
          {library.length === 0 && (
            <div className="col-span-2 text-center py-10 text-gray-400 bg-white rounded-xl border border-dashed">
              No papers in your library yet. Translate one to get started!
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left pt-8">
        <FeatureCard
          title="Gemini Translation"
          desc="High-quality academic translation using the latest Gemini 3.0 Pro/Flash models."
          delay="0"
        />
        <FeatureCard
          title="Split View"
          desc="Read original and translated text side-by-side for perfect context."
          delay="100"
        />
        <FeatureCard
          title="Cloud Sync"
          desc="Your papers and comments synced across all your devices."
          delay="200"
        />
      </div>
    </div>

  );
}

function FeatureCard({ title, desc, delay }: { title: string, desc: string, delay: string }) {
  return (
    <div
      className="p-6 bg-white rounded-xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
      style={{ animationDelay: `${delay}ms` }}
    >
      <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-600 leading-relaxed">{desc}</p>
    </div>
  )
}
