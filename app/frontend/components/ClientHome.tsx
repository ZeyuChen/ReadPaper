'use client';

import Image from 'next/image';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useSession, signOut } from 'next-auth/react';
import SplitView from '@/components/SplitView';
import { Search, Loader2, Trash2, LogOut, BookOpen, Sparkles, ChevronRight, X, RefreshCw, Shield } from 'lucide-react';

interface ClientHomeProps {
    config: {
        apiUrl: string;
        disableAuth: boolean;
    };
}

interface PaperMeta {
    arxiv_id: string;
    title: string;
    abstract: string;
    authors: string[];
    categories: string[];
    published: string;
    url: string;
}

interface ProgressEntry {
    time: string;
    message: string;
    pct: number;
}

export default function ClientHome({ config }: ClientHomeProps) {
    const [url, setUrl] = useState('');
    const [arxivId, setArxivId] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [statusMessage, setStatusMessage] = useState('');
    const [progress, setProgress] = useState(0);
    const [library, setLibrary] = useState<any[]>([]);
    const [useDeepDive, setUseDeepDive] = useState(false);

    // Paper preview / metadata
    const [previewMeta, setPreviewMeta] = useState<PaperMeta | null>(null);
    const [previewLoading, setPreviewLoading] = useState(false);

    // Search suggestions
    const [searchResults, setSearchResults] = useState<PaperMeta[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const searchTimer = useRef<NodeJS.Timeout | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Progress Log
    const [progressLog, setProgressLog] = useState<ProgressEntry[]>([]);

    // Library UI State
    const [librarySearch, setLibrarySearch] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    const ITEMS_PER_PAGE = 6;

    const filteredLibrary = library.filter((paper: any) => {
        if (!librarySearch) return true;
        const title = (paper.title || '').toLowerCase();
        const id = (paper.id || '').toLowerCase();
        const query = librarySearch.toLowerCase();
        return title.includes(query) || id.includes(query);
    });

    const totalPages = Math.ceil(filteredLibrary.length / ITEMS_PER_PAGE);
    const paginatedLibrary = filteredLibrary.slice(
        (currentPage - 1) * ITEMS_PER_PAGE,
        currentPage * ITEMS_PER_PAGE
    );

    const { data: session } = useSession();
    const isLocalDev = config.disableAuth;

    const getAuthHeaders = (): HeadersInit => {
        const headers: HeadersInit = { 'Content-Type': 'application/json' };
        if (isLocalDev && !session) {
            headers['Authorization'] = `Bearer DEV-TOKEN-local-dev-user`;
            return headers;
        }
        // @ts-ignore
        if (session?.idToken) { headers['Authorization'] = `Bearer ${session.idToken}`; }
        return headers;
    };

    useEffect(() => {
        if (session || isLocalDev) fetchLibrary();
    }, [arxivId, session, isLocalDev]);

    const fetchLibrary = async () => {
        if (!session && !isLocalDev) return;
        try {
            const res = await fetch(`${config.apiUrl}/library`, { headers: getAuthHeaders() });
            if (res.ok) setLibrary(await res.json());
        } catch (e) { console.error("Failed to fetch library", e); }
    };

    // Fetch paper metadata for preview (when user pastes arXiv URL)
    const fetchMetadata = useCallback(async (id: string) => {
        setPreviewLoading(true);
        setPreviewMeta(null);
        try {
            const res = await fetch(`${config.apiUrl}/metadata/${id}`);
            if (res.ok) setPreviewMeta(await res.json());
        } catch (e) { /* ignore */ }
        finally { setPreviewLoading(false); }
    }, [config.apiUrl]);

    // Trigger search suggestions when user types non-URL text
    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setUrl(val);
        setError('');
        setPreviewMeta(null);

        // If pasted an arXiv URL → extract ID and show preview
        const arxivMatch = val.match(/(\d{4}\.\d{4,5})/);
        if (arxivMatch && val.includes('arxiv.org')) {
            setShowSuggestions(false);
            fetchMetadata(arxivMatch[1]);
            return;
        }

        // Otherwise trigger keyword search after debounce
        if (val.trim().length >= 3 && !val.includes('arxiv.org')) {
            if (searchTimer.current) clearTimeout(searchTimer.current);
            searchTimer.current = setTimeout(() => {
                doSearch(val.trim());
            }, 500);
        } else {
            setSearchResults([]);
            setShowSuggestions(false);
        }
    };

    const doSearch = async (query: string) => {
        setSearchLoading(true);
        setShowSuggestions(true);
        try {
            const res = await fetch(`${config.apiUrl}/search?q=${encodeURIComponent(query)}&max_results=6`);
            if (res.ok) setSearchResults(await res.json());
        } catch (e) { /* ignore */ }
        finally { setSearchLoading(false); }
    };

    const selectSearchResult = (paper: PaperMeta) => {
        setUrl(`https://arxiv.org/abs/${paper.arxiv_id}`);
        setPreviewMeta(paper);
        setShowSuggestions(false);
        setSearchResults([]);
    };

    const startTranslation = async (targetUrl: string, targetId: string) => {
        setError('');
        setStatusMessage('');
        setProgressLog([]);

        if (!session && !isLocalDev) {
            setError("Please sign in to read papers.");
            return;
        }

        setLoading(true);
        setStatusMessage('Initializing translation...');

        const addLog = (msg: string, pct: number) => {
            const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            setProgressLog(prev => [...prev.slice(-49), { time, message: msg, pct }]);
        };

        try {
            const response = await fetch(`${config.apiUrl}/translate`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ arxiv_url: targetUrl, model: 'flash', deepdive: useDeepDive }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (errData.status === 'completed' || errData.message === 'Already completed') {
                    setArxivId(targetId);
                    setLoading(false);
                    return;
                }
                throw new Error(errData.detail || 'Translation request failed');
            }

            addLog('Translation started ✓', 0);

            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`${config.apiUrl}/status/${targetId}`, { headers: getAuthHeaders() });
                    const statusData = await statusRes.json();

                    if (statusData.message) {
                        setStatusMessage(statusData.message);
                        if (typeof statusData.progress_percent === 'number' && statusData.progress_percent > 0) {
                            addLog(statusData.message, statusData.progress_percent);
                        }
                    }
                    if (typeof statusData.progress_percent === 'number') {
                        setProgress(statusData.progress_percent);
                    }

                    if (statusData.status === 'completed') {
                        clearInterval(pollInterval);
                        addLog('✅ Translation complete! Opening reader...', 100);
                        setTimeout(() => {
                            setArxivId(targetId);
                            setLoading(false);
                            setStatusMessage('');
                            setProgress(0);
                        }, 800);
                    } else if (statusData.status === 'failed') {
                        clearInterval(pollInterval);
                        addLog(`❌ Failed: ${statusData.message}`, 0);
                        setError(`Translation failed: ${statusData.message || 'Unknown error'}`);
                        setLoading(false);
                        setStatusMessage('');
                        setProgress(0);
                    }
                } catch (e) { console.error("Polling error", e); }
            }, 1000);

        } catch (err: any) {
            setError(err.message || 'An error occurred');
            setLoading(false);
            setStatusMessage('');
        }
    };

    const handleTranslate = async (e: React.FormEvent) => {
        e.preventDefault();
        setShowSuggestions(false);
        const matches = url.match(/(\d{4}\.\d{4,5})/);
        const extractedId = matches ? matches[1] : null;
        if (!extractedId) {
            setError('Please enter a valid arXiv URL or search for a paper above');
            return;
        }
        await startTranslation(url, extractedId);
    };

    const handleLucky = async () => {
        setShowSuggestions(false);
        try {
            const res = await fetch(`${config.apiUrl}/search?q=machine+learning&max_results=20`);
            if (res.ok) {
                const papers: PaperMeta[] = await res.json();
                const pick = papers[Math.floor(Math.random() * papers.length)];
                if (pick) {
                    setUrl(`https://arxiv.org/abs/${pick.arxiv_id}`);
                    setPreviewMeta(pick);
                }
            }
        } catch (e) { /* ignore */ }
    };

    const deletePaper = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (!confirm('Delete this paper?')) return;
        try {
            const res = await fetch(`${config.apiUrl}/library/${id}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });
            if (res.ok) setLibrary((prev: any[]) => prev.filter((p: any) => p.id !== id));
        } catch (e) { console.error("Delete failed", e); }
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

    // -- Render --
    return (
        <div className="flex min-h-screen flex-col items-center p-8 bg-gradient-to-br from-slate-50 to-blue-50/30 relative font-sans">
            {/* Header */}
            <div className="absolute top-6 right-8 flex items-center gap-4">
                {!isLocalDev && !session ? (
                    <button
                        onClick={() => window.location.href = '/login'}
                        className="bg-[#1a73e8] hover:bg-[#1557b0] text-white px-6 py-2 rounded-full text-sm font-medium transition-colors shadow-sm"
                    >
                        Sign In
                    </button>
                ) : (
                    <div className="flex items-center gap-3">
                        {/* Admin link — only visible to super admin */}
                        {session?.user?.email === 'chinachenzeyu@gmail.com' && (
                            <a
                                href="/admin"
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[#1a73e8] bg-blue-50 hover:bg-blue-100 rounded-full transition-colors border border-blue-100"
                                title="Admin Dashboard"
                            >
                                <Shield size={12} /> Admin
                            </a>
                        )}
                        <div className="flex flex-col items-end mr-1">
                            <span className="text-xs font-medium text-gray-700">{session?.user?.name || 'Local Dev'}</span>
                            <span className="text-[10px] text-gray-500">{session?.user?.email}</span>
                        </div>
                        <button onClick={() => signOut()} className="relative group focus:outline-none" title="Sign Out">
                            {session?.user?.image ? (
                                <div className="h-9 w-9 rounded-full overflow-hidden border border-gray-200 hover:shadow-md transition-shadow">
                                    <Image src={session.user.image} alt="Profile" width={36} height={36} />
                                </div>
                            ) : (
                                <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium">
                                    {(session?.user?.name?.[0] || 'U').toUpperCase()}
                                </div>
                            )}
                            <div className="absolute -bottom-1 -right-1 bg-white rounded-full p-0.5 border border-gray-100 opacity-0 group-hover:opacity-100 transition-opacity">
                                <LogOut size={10} className="text-gray-600" />
                            </div>
                        </button>
                    </div>
                )}
            </div>

            <div className="w-full max-w-3xl mt-16 space-y-8 text-center">
                {/* Logo + Title */}
                <div className="flex flex-col items-center space-y-4">
                    <div className="relative w-16 h-16">
                        <Image src="/logo.svg" alt="ReadPaper Logo" fill className="object-contain" priority />
                    </div>
                    <div>
                        <h1 className="text-5xl font-light tracking-tight text-[#202124]">ReadPaper</h1>
                        <p className="text-base text-[#5f6368] mt-2">Bilingual arXiv reading experience powered by Gemini</p>
                    </div>
                </div>

                {/* Search / URL Input */}
                <form onSubmit={handleTranslate} className="w-full" autoComplete="off">
                    <div className="relative w-full">
                        <div className="absolute inset-y-0 left-0 flex items-center pl-5 pointer-events-none text-gray-400">
                            {searchLoading ? <Loader2 size={20} className="animate-spin" /> : <Search size={20} />}
                        </div>
                        <input
                            ref={inputRef}
                            id="arxiv-url-input"
                            type="text"
                            placeholder="Paste arXiv URL or search by title / keyword..."
                            className="w-full py-4 pl-14 pr-12 text-[#202124] bg-white border border-[#dfe1e5] rounded-full shadow-sm hover:shadow-md focus:shadow-md outline-none transition-all text-base"
                            value={url}
                            onChange={handleInputChange}
                            onFocus={() => searchResults.length > 0 && setShowSuggestions(true)}
                            disabled={loading}
                            autoComplete="off"
                        />
                        {url && (
                            <button type="button" onClick={() => { setUrl(''); setPreviewMeta(null); setShowSuggestions(false); setError(''); }}
                                className="absolute inset-y-0 right-5 flex items-center text-gray-400 hover:text-gray-600">
                                <X size={16} />
                            </button>
                        )}

                        {/* Search Suggestions Dropdown */}
                        {showSuggestions && searchResults.length > 0 && (
                            <div className="absolute left-0 right-0 top-full mt-2 bg-white border border-gray-200 rounded-2xl shadow-xl z-50 overflow-hidden text-left">
                                {searchResults.map((paper) => (
                                    <button
                                        key={paper.arxiv_id}
                                        type="button"
                                        className="w-full px-5 py-3.5 hover:bg-blue-50 transition-colors text-left border-b border-gray-100 last:border-0 flex gap-3"
                                        onClick={() => selectSearchResult(paper)}
                                    >
                                        <BookOpen size={16} className="text-blue-400 mt-1 flex-shrink-0" />
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium text-gray-900 truncate">{paper.title}</p>
                                            <p className="text-xs text-gray-500 mt-0.5 truncate">
                                                {paper.authors.slice(0, 2).join(', ')}{paper.authors.length > 2 ? ' et al.' : ''} · {paper.arxiv_id}
                                            </p>
                                        </div>
                                        <ChevronRight size={14} className="ml-auto text-gray-400 mt-1 flex-shrink-0" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Paper Preview Card */}
                    {(previewMeta || previewLoading) && !loading && (
                        <div className="mt-4 bg-white border border-blue-100 rounded-2xl p-5 text-left shadow-sm">
                            {previewLoading ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 size={16} className="animate-spin" />
                                    <span className="text-sm">Loading paper info...</span>
                                </div>
                            ) : previewMeta && (
                                <>
                                    <div className="flex gap-2 flex-wrap mb-2">
                                        {previewMeta.categories.slice(0, 3).map(c => (
                                            <span key={c} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{c}</span>
                                        ))}
                                    </div>
                                    <h3 className="text-sm font-semibold text-gray-900 leading-snug mb-1">{previewMeta.title}</h3>
                                    <p className="text-xs text-gray-500 mb-2">
                                        {previewMeta.authors.slice(0, 3).join(', ')}{previewMeta.authors.length > 3 ? ' et al.' : ''} · arXiv:{previewMeta.arxiv_id}
                                    </p>
                                    <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">{previewMeta.abstract}</p>
                                </>
                            )}
                        </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex gap-3 justify-center mt-5">
                        <button
                            id="read-paper-btn"
                            type="submit"
                            disabled={loading}
                            className="bg-[#f8f9fa] hover:bg-[#f1f3f4] text-[#202124] px-7 py-2.5 rounded-full text-sm font-medium border border-[#dfe1e5] transition-all hover:shadow-sm disabled:opacity-60 flex items-center gap-2"
                        >
                            {loading ? <><Loader2 size={14} className="animate-spin" />Reading...</> : <><BookOpen size={14} />Read Paper</>}
                        </button>
                        <button
                            type="button"
                            onClick={handleLucky}
                            disabled={loading}
                            className="bg-[#f8f9fa] hover:bg-[#f1f3f4] text-[#202124] px-7 py-2.5 rounded-full text-sm font-medium border border-[#dfe1e5] transition-all hover:shadow-sm disabled:opacity-60 flex items-center gap-2"
                        >
                            <Sparkles size={14} />I&apos;m Feeling Lucky
                        </button>
                    </div>

                    {/* Deep Dive Toggle */}
                    <div className="flex items-center justify-center gap-2 mt-4">
                        <input
                            type="checkbox"
                            id="deepdive-toggle"
                            checked={useDeepDive}
                            onChange={(e) => setUseDeepDive(e.target.checked)}
                            className="w-4 h-4 accent-blue-600 cursor-pointer"
                            disabled={loading}
                        />
                        <label htmlFor="deepdive-toggle" className="text-sm text-[#5f6368] cursor-pointer select-none flex items-center gap-1">
                            <Sparkles size={13} className="text-blue-400" /> Enable Deep Dive (AI Analysis)
                        </label>
                    </div>
                </form>

                {/* Error Banner */}
                {error && (
                    <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 px-5 py-3.5 rounded-2xl text-sm">
                        <span className="flex-1">{error}</span>
                        <button onClick={() => setError('')} className="text-red-400 hover:text-red-600"><X size={16} /></button>
                        {url.includes('arxiv.org') && (
                            <button onClick={() => handleTranslate({ preventDefault: () => { } } as any)}
                                className="flex items-center gap-1 text-xs bg-red-100 hover:bg-red-200 px-3 py-1.5 rounded-full transition-colors">
                                <RefreshCw size={11} /> Retry
                            </button>
                        )}
                    </div>
                )}

                {/* Progress Panel */}
                {loading && (
                    <div className="bg-white border border-gray-200 rounded-2xl p-5 text-left shadow-sm space-y-3">
                        {/* Progress Bar */}
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-gray-700 truncate flex-1">{statusMessage || 'Initializing...'}</span>
                            <span className="text-sm font-semibold text-blue-600 ml-3 tabular-nums">{progress}%</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                            <div
                                className="h-2 bg-gradient-to-r from-blue-500 to-blue-400 rounded-full transition-all duration-500"
                                style={{ width: `${Math.max(progress, 3)}%` }}
                            />
                        </div>

                        {/* Live Log */}
                        {progressLog.length > 0 && (
                            <div className="max-h-36 overflow-y-auto space-y-1 pt-2 border-t border-gray-100">
                                {[...progressLog].reverse().map((entry, i) => (
                                    <div key={i} className={`flex items-start gap-2 text-xs ${i === 0 ? 'text-blue-700 font-medium' : 'text-gray-500'}`}>
                                        <span className="font-mono opacity-60 flex-shrink-0">{entry.time}</span>
                                        <span className="truncate">{entry.message}</span>
                                        {entry.pct > 0 && <span className="ml-auto flex-shrink-0 tabular-nums opacity-60">{entry.pct}%</span>}
                                    </div>
                                ))}
                            </div>
                        )}

                        <p className="text-xs text-gray-400 text-center">Translation typically takes 2–8 minutes depending on paper length</p>
                    </div>
                )}

                {/* Library */}
                <div className="text-left space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-medium text-gray-800 flex items-center gap-2">
                            My Library
                            <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">{library.length} papers</span>
                        </h2>
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search library..."
                                value={librarySearch}
                                onChange={(e) => setLibrarySearch(e.target.value)}
                                className="pl-8 pr-4 py-1.5 text-sm border border-gray-200 rounded-full focus:outline-none focus:border-blue-300 bg-white"
                            />
                        </div>
                    </div>

                    {paginatedLibrary.length === 0 ? (
                        <div className="border-2 border-dashed border-gray-200 rounded-2xl p-12 text-center bg-white/50">
                            <BookOpen size={32} className="mx-auto text-gray-300 mb-3" />
                            <p className="text-sm text-gray-500">
                                {librarySearch ? 'No matching papers' : 'Your translated papers will appear here'}
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-3">
                            {paginatedLibrary.map((paper: any) => (
                                <div
                                    key={paper.id}
                                    className="group bg-white border border-gray-200 hover:border-blue-200 rounded-2xl p-4 cursor-pointer transition-all hover:shadow-md flex gap-4 items-start"
                                    onClick={() => setArxivId(paper.id)}
                                >
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2 group-hover:text-blue-700 transition-colors">{paper.title || paper.id}</p>
                                        {paper.authors && (
                                            <p className="text-xs text-gray-500 mt-1 truncate">
                                                {paper.authors.slice(0, 2).join(', ')}{paper.authors.length > 2 ? ' et al.' : ''}
                                            </p>
                                        )}
                                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                                            <span className="text-xs text-gray-400 font-mono">{paper.id}</span>
                                            {paper.categories?.slice(0, 2).map((c: string) => (
                                                <span key={c} className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full">{c}</span>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                                        <ChevronRight size={16} className="text-gray-300 group-hover:text-blue-400 transition-colors mt-1" />
                                        <button
                                            onClick={(e) => deletePaper(e, paper.id)}
                                            className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-500 p-1"
                                            title="Delete"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div className="flex justify-center gap-2 pt-2">
                            {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                                <button
                                    key={page}
                                    onClick={() => setCurrentPage(page)}
                                    className={`w-8 h-8 rounded-full text-sm font-medium transition-colors ${page === currentPage
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-white text-gray-600 border border-gray-200 hover:border-blue-300'
                                        }`}
                                >
                                    {page}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Auth notice */}
                {!isLocalDev && !session && (
                    <p className="text-sm text-gray-500 pb-4">
                        Note: You need to <button onClick={() => window.location.href = '/login'} className="text-blue-600 hover:underline">sign in</button> to read papers and save them to your library.
                    </p>
                )}
            </div>
        </div>
    );
}

// ── TaskMonitor (unchanged) ─────────────────────────────────────────────────
function TaskMonitor({ config }: ClientHomeProps) {
    const [tasks, setTasks] = useState<any[]>([]);
    const { data: session } = useSession();
    const isLocalDev = config.disableAuth;

    useEffect(() => {
        const fetchTasks = async () => {
            try {
                const headers: HeadersInit = {};
                // @ts-ignore
                if (session?.idToken) {
                    // @ts-ignore
                    headers['Authorization'] = `Bearer ${session.idToken}`;
                } else if (isLocalDev) {
                    headers['Authorization'] = 'Bearer DEV-TOKEN-local-dev-user';
                } else {
                    return;
                }
                const res = await fetch(`${config.apiUrl}/tasks`, { headers });
                if (res.ok) setTasks(await res.json());
            } catch (e) { console.error("Failed to fetch tasks", e); }
        };

        fetchTasks();
        const interval = setInterval(fetchTasks, 3000);
        return () => clearInterval(interval);
    }, [session, isLocalDev, config.apiUrl]);

    if (tasks.length === 0) return null;

    return (
        <div className="fixed bottom-4 right-4 bg-white border border-gray-200 rounded-2xl shadow-lg p-4 max-w-xs w-full z-50">
            <p className="text-xs font-semibold text-gray-700 mb-2">Active Tasks</p>
            {tasks.map((task: any) => (
                <div key={task.arxiv_id} className="text-xs text-gray-600 mb-1">
                    <span className="font-mono">{task.arxiv_id}</span>: {task.status} ({task.progress_percent}%)
                </div>
            ))}
        </div>
    );
}
