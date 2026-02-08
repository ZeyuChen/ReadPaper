'use client';

import { useState, useEffect } from 'react';
import SplitView from '@/components/SplitView';
import { Search, Loader2, Trash2 } from 'lucide-react';

export default function Home() {
  const [url, setUrl] = useState('');
  // const [model, setModel] = useState('flash'); // Removed, default to flash
  const [arxivId, setArxivId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [progress, setProgress] = useState(0);
  const [library, setLibrary] = useState<any[]>([]);
  const [useDeepDive, setUseDeepDive] = useState(false);

  // Library UI State
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 6;

  // Filter and Pagination Logic
  const filteredLibrary = library.filter((paper: any) => {
    if (!searchTerm) return true;
    const title = (paper.title || '').toLowerCase();
    const id = (paper.id || '').toLowerCase();
    const query = searchTerm.toLowerCase();
    return title.includes(query) || id.includes(query);
  });

  const totalPages = Math.ceil(filteredLibrary.length / ITEMS_PER_PAGE);
  const paginatedLibrary = filteredLibrary.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  useEffect(() => {
    fetchLibrary();
  }, [arxivId]); // Reload when returning from split view

  const fetchLibrary = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/library`);
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

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

      // Call Backend
      const response = await fetch(`${apiUrl}/translate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ arxiv_url: url, model: 'flash', deepdive: useDeepDive }),
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
          const statusRes = await fetch(`${apiUrl}/status/${extractedId}`);
          const statusData = await statusRes.json();
          // console.log("Status:", statusData.status, "Progress:", statusData.progress, "Message:", statusData.message);

          if (statusData.message) {
            setStatusMessage(statusData.message);
          }
          if (typeof statusData.progress === 'number') {
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

  const deletePaper = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation(); // Prevent card click
    if (!confirm('Are you sure you want to delete this paper? This will remove all translated files.')) return;

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/library/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setLibrary((prev: any[]) => prev.filter((p: any) => p.id !== id));
      } else {
        alert("Failed to delete paper");
      }
    } catch (e) {
      console.error("Delete failed", e);
      alert("Delete failed");
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

        <div className="flex items-center justify-center gap-2 text-sm text-gray-600 cursor-pointer" onClick={() => setUseDeepDive(!useDeepDive)}>
          <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${useDeepDive ? 'bg-blue-600 border-blue-600' : 'bg-white border-gray-300'}`}>
            {useDeepDive && <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" /></svg>}
          </div>
          <span>Enable Deep Dive (AI Analysis)</span>
        </div>

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
        <div className="flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
          <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            My Library <span className="text-sm font-normal text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">{library.length}</span>
          </h2>

          {/* Library Search */}
          <div className="relative w-full md:w-64">
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-gray-400">
              <Search size={16} />
            </div>
            <input
              type="text"
              placeholder="Search title..."
              className="w-full py-2 pl-9 pr-4 text-sm text-gray-900 bg-white border border-gray-200 rounded-lg shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-200 outline-none transition-all"
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setCurrentPage(1); // Reset to first page on search
              }}
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-2">
          {paginatedLibrary.map((paper: any) => (
            <div
              key={paper.id}
              onClick={() => setArxivId(paper.id)}
              className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 hover:shadow-md hover:border-blue-200 transition cursor-pointer group flex flex-col h-full"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{paper.id}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{new Date(paper.added_at).toLocaleDateString()}</span>
                  <button
                    onClick={(e) => deletePaper(e, paper.id)}
                    className="text-gray-400 hover:text-red-500 transition-colors p-1"
                    title="Delete Paper"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
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

          {library.length > 0 && paginatedLibrary.length === 0 && (
            <div className="col-span-2 text-center py-10 text-gray-400 bg-white rounded-xl border border-dashed">
              No papers found matching "{searchTerm}".
            </div>
          )}
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex justify-center items-center gap-4 mt-8">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-sm text-gray-600">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <div className="w-full max-w-4xl px-4 py-8">
        <TaskMonitor />
      </div>
    </div>
  );
}

function TaskMonitor() {
  const [tasks, setTasks] = useState<any[]>([]);

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/tasks`);
        if (res.ok) {
          const data = await res.json();
          // Filter to show interesting tasks (processing, failed, or completed recently)
          // For now show all
          setTasks(data);
        }
      } catch (e) {
        console.error("Failed to fetch tasks", e);
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 2000);
    return () => clearInterval(interval);
  }, []);

  if (tasks.length === 0) return null;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-100 flex justify-between items-center">
        <h3 className="font-semibold text-gray-700 flex items-center gap-2">
          <Loader2 size={16} className="animate-spin text-blue-500" />
          Real-time System Status
        </h3>
        <span className="text-xs text-gray-500">Auto-refreshing</span>
      </div>
      <div className="divide-y divide-gray-50">
        {tasks.map((task) => (
          <div key={task.arxiv_id} className="px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors">
            <div className="flex-1 min-w-0 pr-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-medium text-gray-500 bg-gray-100 px-1.5 rounded">
                  {task.arxiv_id}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${task.status === 'completed' ? 'bg-green-100 text-green-700' :
                  task.status === 'failed' ? 'bg-red-100 text-red-700' :
                    'bg-blue-100 text-blue-700'
                  }`}>
                  {task.status}
                </span>
              </div>
              <p className="text-sm text-gray-600 truncate">{task.message}</p>
              {task.details && <p className="text-xs text-gray-400 mt-0.5">{task.details}</p>}
            </div>

            {task.status === 'processing' && (
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <span className="text-sm font-medium text-blue-600">{task.progress}%</span>
                </div>
                <div className="w-16 h-1.5 bg-blue-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
