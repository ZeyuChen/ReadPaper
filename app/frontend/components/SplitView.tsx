'use client';

import React, { useState, useEffect } from 'react';
import { ArrowRight, RefreshCw, Download, Book, Plus, Menu, X, ArrowLeft, Loader2 } from 'lucide-react';
import { useSession } from 'next-auth/react';

interface Paper {
    id: string;
    title?: string;
    added_at: string;
    versions: any[];
}

interface SplitViewProps {
    arxivId: string;
    onPaperSelect: (id: string) => void;
    onBack: () => void;
}

export default function SplitView({ arxivId, onPaperSelect, onBack }: SplitViewProps) {
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
        <div className="flex h-screen bg-gray-100 overflow-hidden">
            {/* Sidebar */}
            <div className={`${showSidebar ? 'w-80' : 'w-0'} bg-white border-r border-gray-200 transition-all duration-300 flex flex-col`}>
                <div className="p-4 border-b flex justify-between items-center bg-gray-50">
                    <h2 className="font-semibold text-gray-700 flex items-center gap-2">
                        <Book size={18} /> Library
                    </h2>
                    <button onClick={() => setShowAddModal(true)} className="p-1.5 bg-blue-100 text-blue-600 rounded-lg hover:bg-blue-200 transition">
                        <Plus size={18} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-2 space-y-2">
                    {papers.map((p) => (
                        <div
                            key={p.id}
                            onClick={() => onPaperSelect(p.id)}
                            className={`p-3 rounded-lg cursor-pointer transition-colors border ${p.id === arxivId ? 'bg-blue-50 border-blue-200 shadow-sm' : 'hover:bg-gray-50 border-transparent hover:border-gray-200'}`}
                        >
                            <div className="font-medium text-gray-900 truncate">{p.title || `arXiv:${p.id}`}</div>
                            <div className="text-xs text-gray-500 mt-1 flex justify-between">
                                <span>{p.id}</span>
                                <span>{new Date(p.added_at).toLocaleDateString()}</span>
                            </div>
                        </div>
                    ))}
                    {papers.length === 0 && (
                        <div className="text-center py-10 text-gray-400 text-sm">
                            No papers yet
                        </div>
                    )}
                </div>

                <div className="p-4 border-t bg-gray-50">
                    <button onClick={onBack} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition font-medium">
                        <ArrowLeft size={16} /> Back to Home
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col h-screen min-w-0">
                {/* Header */}
                <div className="bg-white border-b shadow-sm px-4 py-3 flex justify-between items-center z-10">
                    <div className="flex items-center gap-3">
                        <button onClick={() => setShowSidebar(!showSidebar)} className="p-2 text-gray-500 hover:bg-gray-100 rounded-lg transition">
                            <Menu size={20} />
                        </button>
                        <h1 className="text-lg font-semibold text-gray-800 truncate">
                            Paper: <span className="font-mono text-blue-600 ml-1">{arxivId}</span>
                        </h1>
                    </div>

                    <div className="flex gap-2">
                        <a href={originalUrl} download className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 transition">
                            <Download size={16} /> Original
                        </a>
                        <a href={translatedUrl} download className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 rounded-md hover:bg-blue-100 transition">
                            <Download size={16} /> Translated
                        </a>
                    </div>
                </div>

                {/* Split View */}
                <div className="flex-1 flex overflow-hidden">
                    {/* Left: Original */}
                    <div className="flex-1 bg-gray-200 relative group border-r">
                        <div className="absolute top-2 left-2 z-10 bg-black/60 text-white px-2 py-1 rounded text-xs backdrop-blur-sm shadow-sm pointer-events-none">
                            Original Source
                        </div>
                        <AuthenticatedPdfViewer url={originalUrl} title="Original" />
                    </div>
                    {/* Right: Translated */}
                    <div className="flex-1 bg-white relative group">
                        <div className="absolute top-2 left-2 z-10 bg-blue-600/90 text-white px-2 py-1 rounded text-xs backdrop-blur-sm shadow-sm pointer-events-none">
                            Gemini Translated
                        </div>
                        <AuthenticatedPdfViewer url={translatedUrl} title="Translated" />
                    </div>
                </div>
            </div>

            {/* Add Paper Modal */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
                        <div className="p-6">
                            <div className="flex justify-between items-center mb-6">
                                <h3 className="text-xl font-bold text-gray-900">Add New Paper</h3>
                                <button onClick={() => !isTranslating && setShowAddModal(false)} className="text-gray-400 hover:text-gray-500 transition">
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleAddPaper} className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">arXiv URL</label>
                                    <input
                                        type="text"
                                        value={newUrl}
                                        onChange={(e) => setNewUrl(e.target.value)}
                                        placeholder="https://arxiv.org/abs/..."
                                        className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none transition text-gray-900"
                                        disabled={isTranslating}
                                    />
                                </div>

                                {addError && <div className="text-red-500 text-sm bg-red-50 p-3 rounded-lg border border-red-100">{addError}</div>}

                                {isTranslating && (
                                    <div className="space-y-2">
                                        <div className="flex justify-between text-xs text-gray-500 font-medium">
                                            <span>{statusMsg || 'Processing...'}</span>
                                            {/* We need state for progress, let's assume we add it */}
                                        </div>
                                        <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-blue-600 transition-all duration-500 ease-out rounded-full"
                                                style={{ width: `${progress}%` }}
                                            />
                                        </div>
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    disabled={isTranslating || !newUrl}
                                    className="w-full py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2"
                                >
                                    {isTranslating ? <><Loader2 className="animate-spin" size={18} /> Processing</> : 'Translate & Read'}
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function AuthenticatedPdfViewer({ url, title }: { url: string, title: string }) {
    const { data: session } = useSession();
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchPdf = async () => {
            if (!session?.idToken) return;
            try {
                setLoading(true);
                setError('');
                const res = await fetch(url, {
                    headers: {
                        // @ts-ignore
                        'Authorization': `Bearer ${session.idToken}`
                    }
                });
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
