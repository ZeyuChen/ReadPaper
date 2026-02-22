'use client';

import Image from 'next/image';
import { useState, useEffect, useRef, useCallback } from 'react';
import SplitView from '@/components/SplitView';
import { Search, Loader2, Trash2, LogOut, BookOpen, Sparkles, ChevronRight, X, RefreshCw, Shield, CheckCircle2, Circle, XCircle, Loader, FileText, ChevronLeft, DownloadCloud, Languages, FileCheck2, Check } from 'lucide-react';

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

interface FileStatus {
    status: 'pending' | 'translating' | 'done' | 'failed';
    batches_done: number;
    batches_total: number;
}

export default function ClientHome({ config }: ClientHomeProps) {
    const [url, setUrl] = useState('');
    const [arxivId, setArxivId] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [statusMessage, setStatusMessage] = useState('');
    const [progress, setProgress] = useState(0);
    // displayProgress is smoothly animated toward `progress` via rAF — never snaps.
    const [displayProgress, setDisplayProgress] = useState(0);
    const displayProgressRef = useRef(0);
    // ID of the paper whose delete button is in the "confirm" state
    const [deletingId, setDeletingId] = useState<string | null>(null);
    const [library, setLibrary] = useState<any[]>([]);

    // Per-file translation status (populated from status.files)
    const [translationFiles, setTranslationFiles] = useState<Record<string, FileStatus>>({});
    // Compile error log (populated from status.compile_log on failure)
    const [compileLog, setCompileLog] = useState('');
    // Token usage tracking
    const [totalInTokens, setTotalInTokens] = useState(0);
    const [totalOutTokens, setTotalOutTokens] = useState(0);

    // LaTeX preview sidebar
    const [previewFile, setPreviewFile] = useState<string | null>(null);
    const [previewType, setPreviewType] = useState<'original' | 'translated'>('translated');
    const [previewContent, setPreviewContent] = useState<string>('');
    const [previewLoading, setPreviewLoading] = useState(false);

    // Paper preview / metadata
    const [previewMeta, setPreviewMeta] = useState<PaperMeta | null>(null);
    const [metaPreviewLoading, setMetaPreviewLoading] = useState(false);

    // Search suggestions
    const [searchResults, setSearchResults] = useState<PaperMeta[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const searchTimer = useRef<NodeJS.Timeout | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Progress Log
    const [progressLog, setProgressLog] = useState<ProgressEntry[]>([]);
    // Elapsed timer (seconds since translation started)
    const [elapsedSeconds, setElapsedSeconds] = useState(0);
    const elapsedTimerRef = useRef<NodeJS.Timeout | null>(null);
    // Dedup: skip addLog if the message is the same as last time
    const lastLoggedMsgRef = useRef<string>('');

    // Smooth progress animation
    useEffect(() => {
        let rafId: number;
        const animate = () => {
            const target = progress;
            const current = displayProgressRef.current;
            const diff = target - current;
            if (Math.abs(diff) < 0.1) {
                displayProgressRef.current = target;
            } else {
                // Move at 0.8% per frame (≈ 48% per second) — fast enough to feel live,
                // slow enough to feel smooth. Never moves backward.
                const step = diff > 0 ? Math.min(diff, 0.8) : 0;
                displayProgressRef.current = current + step;
            }
            setDisplayProgress(Math.round(displayProgressRef.current * 10) / 10);
            rafId = requestAnimationFrame(animate);
        };
        rafId = requestAnimationFrame(animate);
        return () => cancelAnimationFrame(rafId);
    }, [progress]);

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

    const getAuthHeaders = (): HeadersInit => {
        return { 'Content-Type': 'application/json' };
    };

    useEffect(() => {
        fetchLibrary();
    }, [arxivId]);

    const fetchLibrary = async () => {
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
        setElapsedSeconds(0);
        setTotalInTokens(0);
        setTotalOutTokens(0);
        lastLoggedMsgRef.current = '';



        setLoading(true);
        setStatusMessage('Starting...');

        // Start elapsed timer
        if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = setInterval(() => {
            setElapsedSeconds(s => s + 1);
        }, 1000);

        const stopTimer = () => {
            if (elapsedTimerRef.current) {
                clearInterval(elapsedTimerRef.current);
                elapsedTimerRef.current = null;
            }
        };

        // Deduplicated addLog: only append if meaningful content changed
        // Strip volatile parts (token counts) for comparison so heartbeats
        // with same batch counts but different cumulative tokens are not duped.
        const addLog = (msg: string, pct: number) => {
            // Extract the "stable" part of the message for dedup comparison
            // e.g. "Translating appendix.tex... 3/12 batches | In 6,842/Out 5,277 tokens"
            //   -> key: "Translating appendix.tex... 3/12 batches"
            const stableKey = msg.split(' | ')[0].trim();
            if (stableKey === lastLoggedMsgRef.current) return;
            lastLoggedMsgRef.current = stableKey;
            const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            setProgressLog(prev => [...prev.slice(-49), { time, message: msg, pct }]);
        };

        try {
            const response = await fetch(`${config.apiUrl}/translate`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ arxiv_url: targetUrl, model: 'flash' }),
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (errData.status === 'completed' || errData.message === 'Already completed') {
                    setArxivId(targetId);
                    setLoading(false);
                    stopTimer();
                    return;
                }
                throw new Error(errData.detail || 'Translation request failed');
            }

            addLog('Translation started ✓', 0);

            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`${config.apiUrl}/status/${targetId}`, { headers: getAuthHeaders() });

                    // Detect session expiry — the most common cause of stuck progress
                    if (statusRes.status === 401) {
                        clearInterval(pollInterval);
                        stopTimer();
                        setLoading(false);
                        setStatusMessage('');
                        setProgress(0);
                        setError('Session expired. Please sign out and sign back in, then try again.');
                        return;
                    }

                    const statusData = await statusRes.json();

                    if (statusData.message) {
                        setStatusMessage(statusData.message);
                        // Surface ALL status changes to the log (not just pct > 0)
                        addLog(statusData.message, statusData.progress_percent ?? 0);
                    }
                    if (typeof statusData.progress_percent === 'number') {
                        // Monotonic: never decrease progress (protects against out-of-order GCS reads)
                        setProgress(prev => Math.max(prev, statusData.progress_percent));
                    }
                    if (statusData.files && typeof statusData.files === 'object') {
                        setTranslationFiles(statusData.files);
                    }
                    if (statusData.compile_log) {
                        setCompileLog(statusData.compile_log);
                    }
                    // Token usage
                    if (typeof statusData.total_in_tokens === 'number') {
                        setTotalInTokens(statusData.total_in_tokens);
                    }
                    if (typeof statusData.total_out_tokens === 'number') {
                        setTotalOutTokens(statusData.total_out_tokens);
                    }

                    if (statusData.status === 'completed') {
                        clearInterval(pollInterval);
                        stopTimer();
                        addLog('✅ Translation complete! Opening reader...', 100);
                        setTimeout(() => {
                            setArxivId(targetId);
                            setLoading(false);
                            setStatusMessage('');
                            setProgress(0);
                            setTranslationFiles({});
                            setElapsedSeconds(0);
                        }, 800);
                    } else if (statusData.status === 'failed') {
                        clearInterval(pollInterval);
                        stopTimer();
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
            stopTimer();
        }
    };

    const openTexPreview = async (filename: string, type: 'original' | 'translated') => {
        if (!url) return;
        const targetId = url.match(/(\d{4}\.\d{4,5})/)?.[1];
        if (!targetId) return;
        setPreviewFile(filename);
        setPreviewType(type);
        setPreviewContent('');
        setPreviewLoading(true);
        try {
            const res = await fetch(
                `${config.apiUrl}/paper/${targetId}/texfile?name=${encodeURIComponent(filename)}&type=${type}`,
                { headers: getAuthHeaders() }
            );
            if (res.ok) {
                const data = await res.json();
                setPreviewContent(data.content || '');
            } else {
                setPreviewContent('(File not yet available — translation may still be in progress)');
            }
        } catch {
            setPreviewContent('(Failed to load file content)');
        } finally {
            setPreviewLoading(false);
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
        try {
            const res = await fetch(`${config.apiUrl}/library/${id}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });
            if (res.ok) {
                setLibrary((prev: any[]) => prev.filter((p: any) => p.id !== id));
                setDeletingId(null);
            }
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
            <div className="absolute top-6 right-8 flex items-center gap-3">
                <div className="flex flex-col items-end mr-1">
                    <span className="text-xs font-medium text-gray-700">Anonymous</span>
                    <span className="text-[10px] text-gray-500">auth disabled</span>
                </div>
                <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium">
                    A
                </div>
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
                    <div className="bg-white border border-gray-200 rounded-2xl p-6 text-left shadow-sm space-y-5">
                        {/* 3-Stage Stepper UI */}
                        <div className="flex items-center justify-between mb-2 mt-1 px-4 relative">
                            {/* connecting line behind */}
                            <div className="absolute top-4 left-[20%] right-[20%] h-[2px] bg-gray-100 z-0" />

                            {[
                                { step: 1, id: 'prep', label: 'Preparation', icon: DownloadCloud, activeThreshold: 0, doneThreshold: 15 },
                                { step: 2, id: 'trans', label: 'Translation', icon: Languages, activeThreshold: 15, doneThreshold: 90 },
                                { step: 3, id: 'comp', label: 'Compilation', icon: FileCheck2, activeThreshold: 90, doneThreshold: 100 },
                            ].map((s) => {
                                const isActive = progress >= s.activeThreshold && progress < s.doneThreshold && progress < 100;
                                const isDone = progress >= s.doneThreshold || progress === 100;
                                const Icon = s.icon;

                                return (
                                    <div key={s.id} className="relative z-10 flex flex-col items-center gap-2 bg-white px-2">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 ${isDone ? 'bg-green-100 text-green-600' : isActive ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30 scale-110' : 'bg-gray-100 text-gray-400'}`}>
                                            {isDone ? <Check size={16} strokeWidth={3} /> : <Icon size={16} />}
                                        </div>
                                        <span className={`text-[10px] font-bold uppercase tracking-wider ${isDone ? 'text-green-600' : isActive ? 'text-blue-600' : 'text-gray-400'}`}>
                                            {s.label}
                                        </span>
                                    </div>
                                )
                            })}
                        </div>

                        {/* Status Message & Thin Progress Bar */}
                        <div className="space-y-1.5 bg-gray-50/50 rounded-xl p-3 border border-gray-100">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-mono text-gray-600 truncate flex-1 flex items-center gap-2">
                                    <span className="flex-shrink-0 w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                                    {statusMessage || 'Starting...'}
                                </span>
                                <div className="flex items-center gap-3 ml-3 flex-shrink-0">
                                    {elapsedSeconds > 0 && (
                                        <span className="text-[10px] text-gray-400 tabular-nums font-mono">
                                            {Math.floor(elapsedSeconds / 60).toString().padStart(2, '0')}:{(elapsedSeconds % 60).toString().padStart(2, '0')} elapsed
                                        </span>
                                    )}
                                    {(totalInTokens > 0 || totalOutTokens > 0) && (
                                        <span className="text-[10px] text-indigo-400 tabular-nums font-mono" title={`Input: ${totalInTokens.toLocaleString()} / Output: ${totalOutTokens.toLocaleString()}`}>
                                            🔤 {((totalInTokens + totalOutTokens) / 1000).toFixed(1)}k tokens
                                        </span>
                                    )}
                                    <span className="text-xs font-semibold text-blue-600 tabular-nums">{progress}%</span>
                                </div>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-1 overflow-hidden">
                                <div className="h-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full"
                                    style={{ width: `${Math.max(displayProgress, 2)}%`, transition: 'width 0.1s linear' }} />
                            </div>
                            {/* Recent log strip — last 3 unique status entries */}
                            {progressLog.length > 1 && (
                                <div className="pt-1 space-y-0.5">
                                    {progressLog.slice(-3).map((entry, i) => (
                                        <div key={i} className="flex items-center gap-1.5 text-[10px] text-gray-400 font-mono">
                                            <span className="text-gray-300">{entry.time}</span>
                                            <span className="truncate">{entry.message}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Per-file status table */}
                        {Object.keys(translationFiles).length > 0 && (
                            <div className="border border-gray-100 rounded-xl overflow-hidden mt-2">
                                <div className="bg-gray-50 px-3 py-1.5 border-b border-gray-100 flex items-center justify-between">
                                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Translation Files</span>
                                    <span className="text-xs text-gray-400">
                                        {Object.values(translationFiles).filter(f => f.status === 'done').length}/{Object.keys(translationFiles).length} done
                                    </span>
                                </div>
                                <div className="divide-y divide-gray-50 max-h-56 overflow-y-auto">
                                    {Object.entries(translationFiles).map(([name, fs]) => {
                                        const isDone = fs.status === 'done';
                                        const isTranslating = fs.status === 'translating';
                                        const isFailed = fs.status === 'failed';
                                        const isPending = fs.status === 'pending';
                                        return (
                                            <div key={name} className="flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 transition-colors group">
                                                {/* Status icon */}
                                                <div className="flex-shrink-0 w-4">
                                                    {isDone && <CheckCircle2 size={15} className="text-green-500" />}
                                                    {isTranslating && <Loader size={15} className="text-blue-500 animate-spin" />}
                                                    {isPending && <Circle size={15} className="text-gray-300" />}
                                                    {isFailed && <XCircle size={15} className="text-red-400" />}
                                                </div>
                                                {/* Filename */}
                                                <span className={`text-xs font-mono flex-1 truncate ${isDone ? 'text-gray-700' : isTranslating ? 'text-blue-700 font-medium' : isFailed ? 'text-red-500' : 'text-gray-400'}`}>
                                                    {name}
                                                </span>
                                                {/* Mini batch bar for files in progress */}
                                                {isTranslating && fs.batches_total > 0 && (
                                                    <div className="flex items-center gap-1.5 flex-shrink-0">
                                                        <div className="w-16 h-1 bg-gray-100 rounded-full overflow-hidden">
                                                            <div className="h-full bg-blue-400 rounded-full transition-all duration-300"
                                                                style={{ width: `${Math.min(100, (fs.batches_done / fs.batches_total) * 100)}%` }} />
                                                        </div>
                                                        <span className="text-[10px] text-gray-400 tabular-nums">{fs.batches_done}/{fs.batches_total}</span>
                                                    </div>
                                                )}
                                                {isDone && (
                                                    <span className="text-[10px] text-green-500 flex-shrink-0">✓</span>
                                                )}
                                                {/* Preview button — visible on hover */}
                                                <button
                                                    onClick={() => openTexPreview(name, 'translated')}
                                                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-blue-500 flex-shrink-0 transition-opacity p-0.5"
                                                    title="Preview translated LaTeX"
                                                >
                                                    <FileText size={12} />
                                                </button>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        <p className="text-xs text-gray-400 text-center">Translation typically takes 2–8 minutes depending on paper length</p>
                    </div>
                )}

                {/* Compile error panel */}
                {!loading && compileLog && error && (
                    <div className="bg-red-50 border border-red-200 rounded-2xl p-4 text-left">
                        <p className="text-xs font-semibold text-red-700 mb-2 flex items-center gap-1.5">⚠️ LaTeX Compilation Error</p>
                        <pre className="text-[11px] font-mono text-red-800 bg-red-100/60 rounded-lg p-3 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-words leading-relaxed">
                            {compileLog}
                        </pre>
                    </div>
                )}

                {/* LaTeX Preview Sidebar — slides in from the right */}
                {previewFile && (
                    <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setPreviewFile(null)}>
                        {/* Dark backdrop */}
                        <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
                        {/* Drawer */}
                        <div
                            className="relative bg-white shadow-2xl w-full max-w-xl flex flex-col h-full"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 flex-shrink-0">
                                <div className="flex items-center gap-2 min-w-0">
                                    <FileText size={14} className="text-gray-500 flex-shrink-0" />
                                    <span className="text-sm font-mono text-gray-700 truncate">{previewFile}</span>
                                </div>
                                <button onClick={() => setPreviewFile(null)} className="text-gray-400 hover:text-gray-700 ml-2 flex-shrink-0">
                                    <X size={16} />
                                </button>
                            </div>
                            {/* Tabs */}
                            <div className="flex border-b border-gray-100 px-4 flex-shrink-0">
                                {(['translated', 'original'] as const).map(t => (
                                    <button
                                        key={t}
                                        onClick={() => openTexPreview(previewFile, t)}
                                        className={`text-xs px-4 py-2 border-b-2 transition-colors capitalize ${previewType === t
                                            ? 'border-blue-500 text-blue-600 font-medium'
                                            : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                                    >
                                        {t === 'translated' ? '✦ Translated' : 'Original'}
                                    </button>
                                ))}
                            </div>
                            {/* Content */}
                            <div className="flex-1 overflow-auto p-4 bg-gray-50">
                                {previewLoading ? (
                                    <div className="flex items-center justify-center h-full text-gray-400 gap-2">
                                        <Loader2 size={16} className="animate-spin" />
                                        <span className="text-sm">Loading...</span>
                                    </div>
                                ) : (
                                    <pre className="text-[11px] font-mono text-gray-800 leading-relaxed whitespace-pre-wrap break-words">
                                        {previewContent || '(No content available)'}
                                    </pre>
                                )}
                            </div>
                        </div>
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
                                    <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                                        <ChevronRight size={16} className="text-gray-300 group-hover:text-blue-400 transition-colors mt-1" />
                                        {deletingId === paper.id ? (
                                            /* Two-step inline confirm — replaces window.confirm() */
                                            <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                                                <button
                                                    onClick={e => { e.stopPropagation(); setDeletingId(null); }}
                                                    className="text-xs text-gray-500 hover:text-gray-700 px-2 py-0.5 rounded-full border border-gray-200 hover:border-gray-300 transition-colors"
                                                >Cancel</button>
                                                <button
                                                    onClick={e => deletePaper(e, paper.id)}
                                                    className="text-xs text-white bg-red-500 hover:bg-red-600 px-2 py-0.5 rounded-full transition-colors font-medium"
                                                >Delete</button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={e => { e.stopPropagation(); setDeletingId(paper.id); }}
                                                className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-500 p-1"
                                                title="Delete"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        )}
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

            </div>
        </div >
    );
}

// ── TaskMonitor (unchanged) ─────────────────────────────────────────────────
function TaskMonitor({ config }: ClientHomeProps) {
    const [tasks, setTasks] = useState<any[]>([]);

    useEffect(() => {
        const fetchTasks = async () => {
            try {
                const headers: HeadersInit = { 'Content-Type': 'application/json' };
                const res = await fetch(`${config.apiUrl}/tasks`, { headers });
                if (res.ok) setTasks(await res.json());
            } catch (e) { console.error("Failed to fetch tasks", e); }
        };

        fetchTasks();
        const interval = setInterval(fetchTasks, 3000);
        return () => clearInterval(interval);
    }, [config.apiUrl]);

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
