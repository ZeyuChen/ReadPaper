'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    ArrowLeft, Download, Plus, Menu, X, Loader2,
    ZoomIn, ZoomOut, SplitSquareHorizontal, RefreshCw,
    FileText, AlignJustify, PenLine, ChevronLeft
} from 'lucide-react';
import Image from 'next/image';

const API_BASE = '/backend';

type ViewMode = 'split' | 'original' | 'translated';

interface Paper {
    id: string;
    title?: string;
    authors?: string[];
    categories?: string[];
    added_at: string;
    versions: any[];
}

interface SplitViewProps {
    arxivId: string;
    onPaperSelect: (id: string) => void;
    onBack: () => void;
}

// ── Authenticated PDF Viewer ─────────────────────────────────────────────────
function AuthenticatedPdfViewer({
    url,
    title,
    zoom,
    iframeRef,
    onMissing,
}: {
    url: string;
    title: string;
    zoom: number;
    iframeRef?: React.RefObject<HTMLIFrameElement | null>;
    /** Called when the PDF returns a persistent 404/500 — paper needs re-translation */
    onMissing?: () => void;
}) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const localRef = useRef<HTMLIFrameElement>(null);
    const ref = iframeRef ?? localRef;

    // Apply zoom via iframe contentDocument style injection
    useEffect(() => {
        const iframe = ref.current;
        if (!iframe || !blobUrl) return;
        const tryApplyZoom = () => {
            try {
                const doc = iframe.contentDocument;
                if (!doc) return;
                // For PDF.js viewer embedded in browser, inject a zoom meta or CSS
                const style = doc.getElementById('__rp_zoom_style') as HTMLStyleElement | null
                    || (() => {
                        const s = doc.createElement('style');
                        s.id = '__rp_zoom_style';
                        doc.head?.appendChild(s);
                        return s;
                    })();
                style.textContent = `
                    :root { zoom: ${zoom}%; }
                    body  { zoom: ${zoom}%; }
                `;
            } catch {
                // Cross-origin (shouldn't happen for blob URLs) — ignore
            }
        };
        // Apply after load
        iframe.addEventListener('load', tryApplyZoom, { once: true });
        tryApplyZoom();
    }, [zoom, blobUrl, ref]);

    useEffect(() => {
        let isMounted = true;
        let objectUrl: string | null = null;

        const fetchPdf = async (retries = 3) => {
            if (isMounted) { setLoading(true); setError(''); }
            try {
                const res = await fetch(url);
                if (!res.ok) {
                    if (res.status === 404 && retries > 0) {
                        await new Promise(r => setTimeout(r, 1500));
                        if (isMounted) return fetchPdf(retries - 1);
                        return;
                    }
                    // 404 after retries exhausted — file is persistently missing
                    if (res.status === 404) {
                        if (isMounted) onMissing?.();
                        throw new Error('PDF file not found. The paper may need to be re-translated.');
                    }
                    // Try to get a human-readable error from the body
                    const errBody = await res.json().catch(() => ({}));
                    throw new Error(errBody.detail || `Server error (${res.status})`);
                }

                const contentType = res.headers.get('content-type') || '';

                // Signed URL response: backend returns JSON { url: "https://storage.googleapis.com/..." }
                // Use the URL directly as iframe src — iframes have no CORS restrictions.
                if (contentType.includes('application/json')) {
                    const data = await res.json();
                    if (data.url) {
                        if (isMounted) setBlobUrl(data.url);
                        return;
                    }
                }

                // Fallback: direct PDF blob (local dev or signed URL failure)
                const blob = await res.blob();
                objectUrl = URL.createObjectURL(blob);
                if (isMounted) setBlobUrl(objectUrl);
            } catch (e: any) {
                if (isMounted) setError(e.message ?? 'Unknown error');
            } finally {
                if (isMounted) setLoading(false);
            }
        };

        fetchPdf();
        return () => {
            isMounted = false;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [url]);

    if (loading) return (
        <div className="w-full h-full flex items-center justify-center flex-col gap-3 text-gray-400 bg-gray-50">
            <Loader2 size={28} className="animate-spin text-blue-400" />
            <span className="text-xs">Loading {title} PDF...</span>
        </div>
    );
    if (error) return (
        <div className="w-full h-full flex items-center justify-center flex-col gap-3 p-8 text-center bg-gray-50">
            <div className="text-3xl">📄</div>
            <p className="text-sm font-semibold text-gray-700">{title} PDF unavailable</p>
            <p className="text-xs text-gray-400 max-w-48 leading-relaxed">{error}</p>
            {onMissing && (
                <button
                    onClick={onMissing}
                    className="mt-2 flex items-center gap-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 px-3 py-2 rounded-full transition-colors"
                >
                    <RefreshCw size={11} /> Re-translate paper
                </button>
            )}
        </div>
    );
    if (!blobUrl) return (
        <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">Waiting...</div>
    );

    return (
        <iframe
            ref={ref as React.RefObject<HTMLIFrameElement>}
            src={blobUrl}
            className="w-full h-full border-none"
            title={title}
        />
    );
}

// ── Notes Panel ──────────────────────────────────────────────────────────────
function NotesPanel({ arxivId, onClose }: { arxivId: string; onClose: () => void }) {
    const storageKey = `readpaper_notes_${arxivId}`;
    const [notes, setNotes] = useState('');
    const [saved, setSaved] = useState(false);
    const timer = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        setNotes(localStorage.getItem(storageKey) || '');
    }, [storageKey]);

    const handleChange = (val: string) => {
        setNotes(val);
        setSaved(false);
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
            localStorage.setItem(storageKey, val);
            setSaved(true);
        }, 800);
    };

    return (
        <div className="w-72 flex flex-col border-l border-gray-200 bg-white shadow-lg">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div className="flex items-center gap-2">
                    <PenLine size={14} className="text-blue-500" />
                    <span className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Reading Notes</span>
                </div>
                <div className="flex items-center gap-2">
                    {saved && <span className="text-xs text-green-500">Saved ✓</span>}
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded">
                        <X size={14} />
                    </button>
                </div>
            </div>
            <div className="px-3 py-2 bg-blue-50 border-b border-blue-100">
                <p className="text-[10px] text-blue-600">Notes are saved locally in your browser per paper.</p>
                <p className="text-[10px] text-blue-400 font-mono mt-0.5">arXiv:{arxivId}</p>
            </div>
            <textarea
                value={notes}
                onChange={(e) => handleChange(e.target.value)}
                placeholder={`📝 Your notes for this paper...\n\nTip: Use markdown!\n## Section\n**bold**, _italic_\n- bullet point`}
                className="flex-1 resize-none p-4 text-sm text-gray-700 outline-none font-mono leading-relaxed bg-white placeholder-gray-300"
                spellCheck={false}
            />
            <div className="px-4 py-2 border-t border-gray-100 bg-gray-50">
                <button
                    onClick={() => {
                        const blob = new Blob([notes], { type: 'text/plain' });
                        const a = document.createElement('a');
                        a.href = URL.createObjectURL(blob);
                        a.download = `notes_${arxivId}.txt`;
                        a.click();
                    }}
                    className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
                >
                    <Download size={11} /> Export notes
                </button>
            </div>
        </div>
    );
}

// ── Main SplitView ─────────────────────────────────────────────────────────
export default function SplitView({ arxivId, onPaperSelect, onBack }: SplitViewProps) {
    const [papers, setPapers] = useState<Paper[]>([]);
    const [showSidebar, setShowSidebar] = useState(true);
    const [showNotes, setShowNotes] = useState(false);
    const [showAddModal, setShowAddModal] = useState(false);
    const [viewMode, setViewMode] = useState<ViewMode>('split');
    const [zoom, setZoom] = useState(100);

    // Resizable divider
    const [splitRatio, setSplitRatio] = useState(50); // percent for left panel
    const isDragging = useRef(false);
    const containerRef = useRef<HTMLDivElement>(null);

    // Add Paper State
    const [newUrl, setNewUrl] = useState('');
    const [isTranslating, setIsTranslating] = useState(false);
    const [addError, setAddError] = useState('');
    const [statusMsg, setStatusMsg] = useState('');
    const [progress, setProgress] = useState(0);

    const leftIframeRef = useRef<HTMLIFrameElement | null>(null);
    const rightIframeRef = useRef<HTMLIFrameElement | null>(null);

    const originalUrl = `${API_BASE}/paper/${arxivId}/original`;
    const translatedUrl = `${API_BASE}/paper/${arxivId}/translated`;

    useEffect(() => { fetchLibrary(); }, [arxivId]);

    const getAuthHeaders = (): HeadersInit => {
        return {
            'Content-Type': 'application/json'
        };
    };

    const fetchLibrary = async () => {
        try {
            const res = await fetch(`${API_BASE}/library`, { headers: getAuthHeaders() });
            if (res.ok) setPapers(await res.json());
        } catch (e) { console.error("fetchLibrary failed", e); }
    };

    // ── Resizable Divider ──
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        isDragging.current = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    }, []);

    useEffect(() => {
        const onMove = (e: MouseEvent) => {
            if (!isDragging.current || !containerRef.current) return;
            const rect = containerRef.current.getBoundingClientRect();
            const ratio = ((e.clientX - rect.left) / rect.width) * 100;
            setSplitRatio(Math.min(Math.max(ratio, 20), 80));
        };
        const onUp = () => {
            if (!isDragging.current) return;
            isDragging.current = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        return () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
    }, []);

    // ── Keyboard shortcuts ──
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            if ((e.metaKey || e.ctrlKey) && e.key === '=') { e.preventDefault(); setZoom(z => Math.min(z + 10, 200)); }
            if ((e.metaKey || e.ctrlKey) && e.key === '-') { e.preventDefault(); setZoom(z => Math.max(z - 10, 50)); }
            if ((e.metaKey || e.ctrlKey) && e.key === '0') { e.preventDefault(); setZoom(100); }
            if (e.key === 'n' && !e.metaKey) setShowNotes(n => !n);
            if (e.key === 's' && !e.metaKey) setShowSidebar(s => !s);
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    const handleAddPaper = async (e: React.FormEvent) => {
        e.preventDefault();
        setAddError('');
        setStatusMsg('');
        if (!newUrl.includes('arxiv.org')) { setAddError('Invalid arXiv URL'); return; }
        setIsTranslating(true);
        setStatusMsg('Initializing...');
        try {
            const matches = newUrl.match(/(\d{4}\.\d{4,5})/);
            const extractedId = matches ? matches[1] : null;
            if (!extractedId) throw new Error("Could not extract ID");

            const res = await fetch(`${API_BASE}/translate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
                body: JSON.stringify({ arxiv_url: newUrl, model: 'flash' })
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                if (data.status === 'completed' || data.message === 'Already completed') {
                    setIsTranslating(false); setShowAddModal(false); setNewUrl('');
                    onPaperSelect(extractedId); return;
                }
                throw new Error(data.detail || 'Request failed');
            }

            const poll = setInterval(async () => {
                try {
                    const sRes = await fetch(`${API_BASE}/status/${extractedId}`, { headers: getAuthHeaders() });
                    const sData = await sRes.json();
                    if (sData.message) setStatusMsg(sData.message);
                    if (typeof sData.progress_percent === 'number') setProgress(sData.progress_percent);
                    if (sData.status === 'completed') {
                        clearInterval(poll);
                        setIsTranslating(false); setShowAddModal(false); setNewUrl(''); setProgress(0);
                        fetchLibrary(); onPaperSelect(extractedId);
                    } else if (sData.status === 'failed') {
                        clearInterval(poll);
                        setAddError(sData.message || 'Failed'); setIsTranslating(false); setProgress(0);
                    }
                } catch { /* ignore */ }
            }, 1000);
        } catch (err: any) {
            setAddError(err.message);
            setIsTranslating(false);
        }
    };

    const currentPaper = papers.find(p => p.id === arxivId);

    return (
        <div className="flex h-screen bg-white overflow-hidden font-sans">
            {/* ── Sidebar ── */}
            <div className="relative flex-shrink-0 flex">
                <div className={`${showSidebar ? 'w-64' : 'w-0'
                    } bg-[#f8f9fa] border-r border-[#dadce0] transition-all duration-300 flex flex-col overflow-hidden`}>
                    <div className="p-3 flex items-center justify-between flex-shrink-0">
                        <button onClick={onBack} className="p-2 text-[#5f6368] hover:bg-[#e8eaed] rounded-full transition-colors" title="Back">
                            <ArrowLeft size={18} />
                        </button>
                        <button
                            onClick={() => setShowAddModal(true)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-[#3c4043] border border-[#dadce0] rounded-full hover:shadow-md transition-shadow text-xs font-medium"
                        >
                            <Plus size={14} className="text-[#1a73e8]" /> New
                        </button>
                    </div>

                    <div className="px-3 pb-1">
                        <p className="text-[10px] font-bold text-[#5f6368] uppercase tracking-wider px-2 mb-1">My Library</p>
                    </div>

                    <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
                        {papers.map((p) => (
                            <div
                                key={p.id}
                                onClick={() => onPaperSelect(p.id)}
                                className={`px-3 py-2.5 rounded-lg cursor-pointer transition-all ${p.id === arxivId
                                    ? 'bg-[#e8f0fe] text-[#1967d2]'
                                    : 'text-[#3c4043] hover:bg-[#f1f3f4]'
                                    }`}
                            >
                                <div className="text-xs font-medium leading-snug line-clamp-2">{p.title || `arXiv:${p.id}`}</div>
                                <div className={`text-[10px] font-mono mt-0.5 ${p.id === arxivId ? 'text-[#1967d2]/70' : 'text-[#9aa0a6]'}`}>{p.id}</div>
                            </div>
                        ))}
                        {papers.length === 0 && (
                            <div className="text-center py-8 text-[#9aa0a6] text-xs">No papers yet</div>
                        )}
                    </div>

                    <div className="p-3 border-t border-[#dadce0] flex-shrink-0">
                        <div className="flex items-center gap-2 px-2">
                            <div className="h-5 w-5 rounded-full bg-[#1a73e8] flex items-center justify-center text-white text-[9px]">
                                A
                            </div>
                            <span className="text-[11px] text-[#5f6368] truncate">Anonymous</span>
                        </div>
                    </div>
                </div>

                {/* ── Always-visible sidebar toggle tab ── */}
                <button
                    onClick={() => setShowSidebar(s => !s)}
                    title={showSidebar ? 'Collapse sidebar (S)' : 'Expand sidebar (S)'}
                    className="absolute -right-3 top-1/2 -translate-y-1/2 z-20 w-6 h-12 bg-white border border-[#dadce0] rounded-r-lg shadow-sm flex items-center justify-center text-[#5f6368] hover:text-[#1a73e8] hover:border-[#1a73e8] hover:shadow-md transition-all group"
                >
                    <ChevronLeft
                        size={14}
                        className={`transition-transform duration-300 ${showSidebar ? '' : 'rotate-180'}`}
                    />
                </button>
            </div>

            {/* ── Main Content ── */}
            <div className="flex-1 flex flex-col h-screen min-w-0">
                {/* Header */}
                <div className="bg-white border-b border-[#dadce0] px-3 py-2 flex items-center gap-2 flex-shrink-0 z-10">

                    {/* Title */}
                    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                        <h1 className="text-xs font-semibold text-[#202124] truncate leading-tight">
                            {currentPaper?.title || `arXiv:${arxivId}`}
                        </h1>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[10px] text-[#9aa0a6] font-mono">{arxivId}</span>
                            {currentPaper?.categories?.slice(0, 2).map(c => (
                                <span key={c} className="text-[9px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">{c}</span>
                            ))}
                        </div>
                    </div>

                    {/* View Mode Toggle */}
                    <div className="flex items-center bg-[#f1f3f4] rounded-full p-0.5 gap-0.5 flex-shrink-0">
                        <button
                            onClick={() => setViewMode('original')}
                            className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${viewMode === 'original' ? 'bg-white shadow-sm text-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124]'}`}
                            title="Original only"
                        >
                            <FileText size={12} className="inline mr-1" />EN
                        </button>
                        <button
                            onClick={() => setViewMode('split')}
                            className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${viewMode === 'split' ? 'bg-white shadow-sm text-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124]'}`}
                            title="Split view"
                        >
                            <SplitSquareHorizontal size={12} className="inline mr-1" />Split
                        </button>
                        <button
                            onClick={() => setViewMode('translated')}
                            className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${viewMode === 'translated' ? 'bg-white shadow-sm text-[#1a73e8]' : 'text-[#5f6368] hover:text-[#202124]'}`}
                            title="Translated only"
                        >
                            <AlignJustify size={12} className="inline mr-1" />中文
                        </button>
                    </div>

                    {/* Zoom Controls */}
                    <div className="flex items-center bg-[#f1f3f4] rounded-full px-2 py-0.5 gap-1 flex-shrink-0">
                        <button onClick={() => setZoom(z => Math.max(z - 10, 50))} className="p-1 text-[#5f6368] hover:text-[#202124] transition-colors" title="Zoom out (⌘-)">
                            <ZoomOut size={13} />
                        </button>
                        <button onClick={() => setZoom(100)} className="text-[11px] font-mono text-[#5f6368] hover:text-[#202124] w-9 text-center" title="Reset zoom (⌘0)">
                            {zoom}%
                        </button>
                        <button onClick={() => setZoom(z => Math.min(z + 10, 200))} className="p-1 text-[#5f6368] hover:text-[#202124] transition-colors" title="Zoom in (⌘+)">
                            <ZoomIn size={13} />
                        </button>
                    </div>

                    {/* Notes Button */}
                    <button
                        onClick={() => setShowNotes(n => !n)}
                        className={`p-1.5 rounded-full transition-all flex-shrink-0 ${showNotes ? 'bg-blue-50 text-blue-600' : 'text-[#5f6368] hover:bg-[#f1f3f4]'}`}
                        title="Reading notes (N)"
                    >
                        <PenLine size={16} />
                    </button>

                    {/* Downloads */}
                    <div className="flex gap-1.5 flex-shrink-0">
                        <button
                            onClick={async () => {
                                try {
                                    const res = await fetch(originalUrl);
                                    if (!res.ok) return;
                                    const ct = res.headers.get('content-type') || '';
                                    if (ct.includes('application/json')) {
                                        const data = await res.json();
                                        if (data.url) { window.open(data.url, '_blank'); return; }
                                    }
                                    // Fallback: blob download
                                    const blob = await res.blob();
                                    const u = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = u; a.download = `${arxivId}.pdf`; a.click();
                                    URL.revokeObjectURL(u);
                                } catch (e) { console.error('Download failed', e); }
                            }}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium text-[#3c4043] bg-white border border-[#dadce0] rounded-md hover:bg-[#f8f9fa] transition cursor-pointer"
                        >
                            <Download size={11} /> EN
                        </button>
                        <button
                            onClick={async () => {
                                try {
                                    const res = await fetch(translatedUrl);
                                    if (!res.ok) return;
                                    const ct = res.headers.get('content-type') || '';
                                    if (ct.includes('application/json')) {
                                        const data = await res.json();
                                        if (data.url) { window.open(data.url, '_blank'); return; }
                                    }
                                    // Fallback: blob download
                                    const blob = await res.blob();
                                    const u = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = u; a.download = `${arxivId}_zh.pdf`; a.click();
                                    URL.revokeObjectURL(u);
                                } catch (e) { console.error('Download failed', e); }
                            }}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium text-white bg-[#1a73e8] rounded-md hover:bg-[#1557b0] transition shadow-sm cursor-pointer"
                        >
                            <Download size={11} /> 中文
                        </button>
                    </div>
                </div>



                {/* PDF Area */}
                <div className="flex flex-1 overflow-hidden bg-[#e8eaed]" ref={containerRef}>
                    {/* Left Panel: Original */}
                    {(viewMode === 'split' || viewMode === 'original') && (
                        <div
                            className="flex flex-col bg-white relative"
                            style={{
                                width: viewMode === 'split' ? `${splitRatio}%` : '100%',
                                flexShrink: 0,
                            }}
                        >
                            <div className="absolute top-2 left-3 z-10">
                                <span className="px-2 py-0.5 bg-[#f1f3f4] text-[#5f6368] text-[9px] font-bold rounded uppercase tracking-wider shadow-sm">
                                    Original · EN
                                </span>
                            </div>
                            <div className="flex-1 overflow-hidden">
                                <AuthenticatedPdfViewer
                                    url={originalUrl} title="Original" zoom={zoom}
                                    iframeRef={leftIframeRef}
                                    onMissing={() => { setNewUrl(`https://arxiv.org/abs/${arxivId}`); setShowAddModal(true); }}
                                />
                            </div>
                        </div>
                    )}

                    {/* Resizable Divider */}
                    {viewMode === 'split' && (
                        <div
                            className="w-1.5 flex-shrink-0 bg-[#dadce0] hover:bg-blue-400 active:bg-blue-500 cursor-col-resize transition-colors flex items-center justify-center group"
                            onMouseDown={handleMouseDown}
                            title="Drag to resize"
                        >
                            <div className="h-12 w-0.5 bg-gray-400 group-hover:bg-blue-300 rounded-full opacity-50 group-hover:opacity-100 transition-all" />
                        </div>
                    )}

                    {/* Right Panel: Translated */}
                    {(viewMode === 'split' || viewMode === 'translated') && (
                        <div
                            className="flex flex-col bg-white relative"
                            style={{
                                width: viewMode === 'split' ? `${100 - splitRatio}%` : '100%',
                                flexShrink: 0,
                            }}
                        >
                            <div className="absolute top-2 left-3 z-10">
                                <span className="px-2 py-0.5 bg-[#e8f0fe] text-[#1a73e8] text-[9px] font-bold rounded uppercase tracking-wider shadow-sm">
                                    Translated · 中文
                                </span>
                            </div>
                            <div className="flex-1 overflow-hidden">
                                <AuthenticatedPdfViewer
                                    url={translatedUrl} title="Translated" zoom={zoom}
                                    iframeRef={rightIframeRef}
                                    onMissing={() => { setNewUrl(`https://arxiv.org/abs/${arxivId}`); setShowAddModal(true); }}
                                />
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Notes Panel ── */}
            {showNotes && <NotesPanel arxivId={arxivId} onClose={() => setShowNotes(false)} />}

            {/* ── Add Paper Modal ── */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[2px] p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden border border-[#dadce0]">
                        <div className="p-8">
                            <div className="flex justify-between items-center mb-6">
                                <h3 className="text-xl font-normal text-[#202124]">Translate new paper</h3>
                                <button onClick={() => !isTranslating && setShowAddModal(false)} className="text-[#5f6368] hover:bg-[#f1f3f4] p-1.5 rounded-full transition">
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleAddPaper} className="space-y-6">
                                <div>
                                    <p className="text-sm text-[#5f6368] mb-4">Enter an arXiv URL to begin the bilingual translation process.</p>
                                    <input
                                        type="text"
                                        value={newUrl}
                                        onChange={(e) => setNewUrl(e.target.value)}
                                        placeholder="https://arxiv.org/abs/..."
                                        className="w-full px-4 py-3 bg-white border border-[#dadce0] rounded-lg focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8] outline-none transition text-[#202124] text-sm"
                                        disabled={isTranslating}
                                        autoFocus
                                    />
                                </div>

                                {addError && (
                                    <div className="text-[#d93025] text-xs bg-[#fce8e6] p-3 rounded-lg">{addError}</div>
                                )}

                                {isTranslating && (
                                    <div className="space-y-2">
                                        <div className="flex justify-between text-[11px] text-[#1a73e8] font-semibold">
                                            <span>{statusMsg || 'Processing...'}</span>
                                            <span>{progress}%</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-[#e8f0fe] rounded-full overflow-hidden">
                                            <div className="h-full bg-[#1a73e8] transition-all duration-700" style={{ width: `${progress}%` }} />
                                        </div>
                                    </div>
                                )}

                                <div className="flex justify-end gap-3 pt-2">
                                    <button type="button" onClick={() => setShowAddModal(false)} disabled={isTranslating}
                                        className="px-4 py-2 text-sm font-medium text-[#5f6368] hover:bg-[#f1f3f4] rounded-md transition disabled:opacity-50">
                                        Cancel
                                    </button>
                                    <button type="submit" disabled={isTranslating || !newUrl}
                                        className="px-6 py-2 bg-[#1a73e8] text-white rounded-md text-sm font-medium hover:bg-[#1557b0] transition shadow-sm disabled:opacity-50 flex items-center gap-2">
                                        {isTranslating ? <Loader2 className="animate-spin" size={16} /> : null}
                                        {isTranslating ? 'Translating...' : 'Translate'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
