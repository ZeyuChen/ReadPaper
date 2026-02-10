'use client';

import React, { useState, useEffect } from 'react';
import { ArrowRight, RefreshCw, Download, Book, Plus, Menu, X, ArrowLeft, Loader2 } from 'lucide-react';
import { useSession } from 'next-auth/react';
import Image from 'next/image';

interface Paper {
    id: string;
    title?: string;
    added_at: string;
    versions: any[];
}

interface SplitViewProps {
    /** The ID of the arXiv paper to display */
    arxivId: string;
    /** Callback when a user selects a different paper from the sidebar */
    onPaperSelect: (id: string) => void;
    /** Callback to return to the main home screen */
    onBack: () => void;
}

export default function SplitView({ arxivId, onPaperSelect, onBack }: SplitViewProps) {
    const { data: session } = useSession();
    const [papers, setPapers] = useState<Paper[]>([]);
    const [showSidebar, setShowSidebar] = useState(true);
    const [showAddModal, setShowAddModal] = useState(false);

    // Add Paper State
    const [newUrl, setNewUrl] = useState('');
    const [isTranslating, setIsTranslating] = useState(false);
    const [addError, setAddError] = useState('');
    const [statusMsg, setStatusMsg] = useState('');
    const [progress, setProgress] = useState(0);

    const originalUrl = `http://localhost:8000/paper/${arxivId}/original`;
    const translatedUrl = `http://localhost:8000/paper/${arxivId}/translated`;

    useEffect(() => {
        fetchLibrary();
    }, [arxivId]); // Refresh when ID changes to ensure current is in list

    const fetchLibrary = async () => {
        try {
            const res = await fetch('http://localhost:8000/library');
            if (res.ok) {
                const data = await res.json();
                setPapers(data);
            }
        } catch (e) {
            console.error("Failed to fetch library", e);
        }
    };

    const handleAddPaper = async (e: React.FormEvent) => {
        e.preventDefault();
        setAddError('');
        setStatusMsg('');

        if (!newUrl.includes('arxiv.org')) {
            setAddError('Invalid arXiv URL');
            return;
        }

        setIsTranslating(true);
        setStatusMsg('Initializing...');

        try {
            const matches = newUrl.match(/(\d{4}\.\d{4,5})/);
            const extractedId = matches ? matches[1] : null;

            if (!extractedId) {
                throw new Error("Could not extract ID");
            }

            const res = await fetch('http://localhost:8000/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ arxiv_url: newUrl, model: 'flash' })
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                if (data.status === 'completed' || data.message === 'Already completed') {
                    // Already exists, just switch
                    setIsTranslating(false);
                    setShowAddModal(false);
                    setNewUrl('');
                    onPaperSelect(extractedId);
                    return;
                }
                throw new Error(data.detail || 'Request failed');
            }

            // Poll
            const poll = setInterval(async () => {
                try {
                    const sRes = await fetch(`http://localhost:8000/status/${extractedId}`);
                    const sData = await sRes.json();

                    if (sData.message) setStatusMsg(sData.message);
                    if (typeof sData.progress_percent === 'number') setProgress(sData.progress_percent);

                    if (sData.status === 'completed') {
                        clearInterval(poll);
                        setIsTranslating(false);
                        setShowAddModal(false);
                        setNewUrl('');
                        setProgress(0);
                        fetchLibrary(); // Refresh list
                        onPaperSelect(extractedId); // Switch to new paper
                    } else if (sData.status === 'failed') {
                        clearInterval(poll);
                        setAddError(sData.message || 'Failed');
                        setIsTranslating(false);
                        setProgress(0);
                    }
                } catch (e) {
                    console.error(e);
                }
            }, 1000);

        } catch (err: any) {
            setAddError(err.message);
            setIsTranslating(false);
        }
    };

    return (
        <div className="flex h-screen bg-white overflow-hidden font-sans">
            {/* Sidebar */}
            <div className={`${showSidebar ? 'w-72' : 'w-0'} bg-[#f8f9fa] border-r border-[#dadce0] transition-all duration-300 flex flex-col`}>
                <div className="p-4 flex items-center justify-between">
                    <button
                        onClick={onBack}
                        className="p-2 text-[#5f6368] hover:bg-[#e8eaed] rounded-full transition-colors"
                        title="Back to search"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <button
                        onClick={() => setShowAddModal(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-white text-[#3c4043] border border-[#dadce0] rounded-full hover:shadow-md transition-shadow font-medium text-sm"
                    >
                        <Plus size={18} className="text-[#1a73e8]" />
                        <span>New</span>
                    </button>
                </div>

                <div className="px-4 py-2">
                    <h2 className="text-[11px] font-bold text-[#5f6368] uppercase tracking-wider mb-2 px-2">
                        My Library
                    </h2>
                </div>

                <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
                    {papers.map((p) => (
                        <div
                            key={p.id}
                            onClick={() => onPaperSelect(p.id)}
                            className={`px-4 py-3 rounded-r-full cursor-pointer transition-all flex flex-col gap-0.5 ${p.id === arxivId
                                ? 'bg-[#e8f0fe] text-[#1967d2]'
                                : 'text-[#3c4043] hover:bg-[#f1f3f4]'
                                }`}
                        >
                            <div className="font-medium text-sm truncate">{p.title || `arXiv:${p.id}`}</div>
                            <div className={`text-[10px] ${p.id === arxivId ? 'text-[#1967d2]' : 'text-[#5f6368]'}`}>
                                {p.id}
                            </div>
                        </div>
                    ))}
                    {papers.length === 0 && (
                        <div className="text-center py-10 text-[#5f6368] text-xs">
                            No papers in library
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-[#dadce0]">
                    <div className="flex items-center gap-3 px-2">
                        {session?.user?.image ? (
                            <Image
                                src={session.user.image}
                                alt="Profile"
                                width={24}
                                height={24}
                                className="rounded-full border border-gray-200"
                            />
                        ) : (
                            <div className="h-6 w-6 rounded-full bg-[#1a73e8] flex items-center justify-center text-white text-[10px]">
                                {(session?.user?.name?.[0] || 'U').toUpperCase()}
                            </div>
                        )}
                        <span className="text-xs font-medium text-[#3c4043] truncate">
                            {session?.user?.name || 'User'}
                        </span>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col h-screen min-w-0">
                {/* Header */}
                <div className="bg-white border-b border-[#dadce0] px-4 py-2 flex justify-between items-center z-10">
                    <div className="flex items-center gap-3 overflow-hidden">
                        {!showSidebar && (
                            <button onClick={() => setShowSidebar(true)} className="p-2 text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition">
                                <Menu size={20} />
                            </button>
                        )}
                        <div className="flex flex-col overflow-hidden">
                            <h1 className="text-sm font-medium text-[#202124] truncate">
                                {papers.find(p => p.id === arxivId)?.title || `arXiv:${arxivId}`}
                            </h1>
                            <span className="text-[10px] text-[#5f6368] font-mono">{arxivId}</span>
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <a
                            href={originalUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-[#3c4043] bg-white border border-[#dadce0] rounded-md hover:bg-[#f8f9fa] transition"
                        >
                            <Download size={14} /> Original
                        </a>
                        <a
                            href={translatedUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white bg-[#1a73e8] rounded-md hover:bg-[#1557b0] transition shadow-sm"
                        >
                            <Download size={14} /> Translated
                        </a>
                    </div>
                </div>

                {/* Split View */}
                <div className="flex-1 flex overflow-hidden bg-[#e8eaed]">
                    {/* Left: Original */}
                    <div className="flex-1 bg-white relative group border-r border-[#dadce0]">
                        <div className="absolute top-2 left-4 z-10">
                            <span className="px-2 py-1 bg-[#f1f3f4] text-[#5f6368] text-[10px] font-bold rounded uppercase tracking-wider shadow-sm">
                                Original
                            </span>
                        </div>
                        <AuthenticatedPdfViewer url={originalUrl} title="Original" />
                    </div>
                    {/* Right: Translated */}
                    <div className="flex-1 bg-white relative group">
                        <div className="absolute top-2 left-4 z-10">
                            <span className="px-2 py-1 bg-[#e8f0fe] text-[#1a73e8] text-[10px] font-bold rounded uppercase tracking-wider shadow-sm">
                                Translated
                            </span>
                        </div>
                        <AuthenticatedPdfViewer url={translatedUrl} title="Translated" />
                    </div>
                </div>
            </div>

            {/* Add Paper Modal */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[2px] p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200 border border-[#dadce0]">
                        <div className="p-8">
                            <div className="flex justify-between items-center mb-6">
                                <h3 className="text-xl font-normal text-[#202124]">Translate new paper</h3>
                                <button onClick={() => !isTranslating && setShowAddModal(false)} className="text-[#5f6368] hover:bg-[#f1f3f4] p-1.5 rounded-full transition">
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleAddPaper} className="space-y-6">
                                <div>
                                    <p className="text-sm text-[#5f6368] mb-4">
                                        Enter an arXiv URL to begin the bilingual translation process.
                                    </p>
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
                                    <div className="text-[#d93025] text-xs bg-[#fce8e6] p-3 rounded-lg flex items-center gap-2">
                                        <div className="w-1 h-1 bg-[#d93025] rounded-full"></div>
                                        {addError}
                                    </div>
                                )}

                                {isTranslating && (
                                    <div className="space-y-2">
                                        <div className="flex justify-between text-[11px] text-[#1a73e8] font-bold uppercase tracking-tight">
                                            <span>{statusMsg || 'Processing...'}</span>
                                            <span>{progress}%</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-[#e8f0fe] rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-[#1a73e8] transition-all duration-700 ease-out"
                                                style={{ width: `${progress}%` }}
                                            />
                                        </div>
                                    </div>
                                )}

                                <div className="flex justify-end gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={() => setShowAddModal(false)}
                                        disabled={isTranslating}
                                        className="px-4 py-2 text-sm font-medium text-[#5f6368] hover:bg-[#f1f3f4] rounded-md transition disabled:opacity-50"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={isTranslating || !newUrl}
                                        className="px-6 py-2 bg-[#1a73e8] text-white rounded-md text-sm font-medium hover:bg-[#1557b0] transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    >
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


/**
 * A secure PDF viewer that fetches content using the user's session token.
 * 
 * Unlike standard iframes, this component intercepts the request to add the 
 * Authorization header (Bearer token) before creating a local Blob URL.
 * This ensures that private/user-scoped PDFs cannot be accessed publicly.
 */
function AuthenticatedPdfViewer({ url, title }: { url: string, title: string }) {
    const { data: session } = useSession();
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const isLocalDev = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';

    useEffect(() => {
        const fetchPdf = async () => {
            // @ts-ignore
            if (!session?.idToken && !isLocalDev) return;
            try {
                setLoading(true);
                setError('');
                
                const headers: Record<string, string> = {};
                // @ts-ignore
                if (session?.idToken) {
                    // @ts-ignore
                    headers['Authorization'] = `Bearer ${session.idToken}`;
                } else if (isLocalDev) {
                    headers['Authorization'] = `Bearer DEV-TOKEN-local-dev-user`;
                }

                const res = await fetch(url, { headers });
                if (!res.ok) {
                    if (res.status === 404) throw new Error("PDF not found yet");
                    throw new Error(`Failed to load PDF: ${res.statusText}`);
                }
                const blob = await res.blob();
                const objectUrl = URL.createObjectURL(blob);
                setBlobUrl(objectUrl);
            } catch (e: any) {
                console.error(`PDF Load Error (${title}):`, e);
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchPdf();

        return () => {
            if (blobUrl) URL.revokeObjectURL(blobUrl);
        };
    }, [url, session]);

    if (loading) return <div className="w-full h-full flex items-center justify-center text-gray-500"><Loader2 className="animate-spin mr-2" /> Loading PDF...</div>;
    if (error) return <div className="w-full h-full flex items-center justify-center text-red-500 bg-gray-50 flex-col gap-2"><p>Unable to load PDF</p><p className="text-xs text-gray-400">{error}</p></div>;
    if (!blobUrl) return <div className="w-full h-full flex items-center justify-center text-gray-400">Waiting for content...</div>;

    return <iframe src={blobUrl} className="w-full h-full border-none" title={title} />;
}
