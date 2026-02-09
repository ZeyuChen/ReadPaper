'use client';

import Image from 'next/image';
import { useState, useEffect } from 'react';
import { useSession, signOut } from 'next-auth/react';
import SplitView from '@/components/SplitView';
import { Search, Loader2, Trash2, LogOut, User } from 'lucide-react';

interface ClientHomeProps {
    config: {
        apiUrl: string;
        disableAuth: boolean;
    };
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

    const { data: session } = useSession();
    const isLocalDev = config.disableAuth;

    // Helper for Auth Headers
    const getAuthHeaders = () => {
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
        };

        if (isLocalDev && !session) {
            headers['Authorization'] = `Bearer DEV-TOKEN-local-dev-user`;
            return headers;
        }

        // @ts-ignore
        if (session?.idToken) {
            // @ts-ignore
            headers['Authorization'] = `Bearer ${session.idToken}`;
        }
        return headers;
    };

    useEffect(() => {
        if (session || isLocalDev) fetchLibrary();
    }, [arxivId, session, isLocalDev]);

    const fetchLibrary = async () => {
        if (!session && !isLocalDev) return;
        try {
            const res = await fetch(`${config.apiUrl}/library`, {
                headers: getAuthHeaders()
            });
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

        if (!session && !isLocalDev) {
            setError("Please sign in to read papers.");
            return;
        }

        // Simple verification
        if (!url.includes('arxiv.org')) {
            setError('Please enter a valid arXiv URL');
            return;
        }

        setLoading(true);
        setStatusMessage('Initializing translation...');

        try {
            const matches = url.match(/(\d{4}\.\d{4,5})/);
            const extractedId = matches ? matches[1] : null;

            if (!extractedId) {
                throw new Error("Could not extract arXiv ID");
            }

            // Call Backend
            const response = await fetch(`${config.apiUrl}/translate`, {
                method: 'POST',
                headers: getAuthHeaders(),
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
                    const statusRes = await fetch(`${config.apiUrl}/status/${extractedId}`, {
                        headers: getAuthHeaders()
                    });
                    const statusData = await statusRes.json();

                    if (statusData.message) {
                        setStatusMessage(statusData.message);
                    }
                    if (typeof statusData.progress_percent === 'number') {
                        setProgress(statusData.progress_percent);
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
            const res = await fetch(`${config.apiUrl}/library/${id}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
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
        <div className="flex min-h-screen flex-col items-center p-8 bg-white relative font-sans">
            {/* Header / User Profile */}
            <div className="absolute top-6 right-8 flex items-center gap-4">
                {!isLocalDev && !session ? (
                    <button
                        onClick={() => window.location.href = '/login'}
                        className="bg-[#1a73e8] hover:bg-[#1557b0] text-white px-6 py-2 rounded-md text-sm font-medium transition-colors shadow-none"
                    >
                        Sign In
                    </button>
                ) : (
                    <div className="flex items-center gap-3">
                        <div className="flex flex-col items-end mr-1">
                            <span className="text-xs font-medium text-gray-700">
                                {session?.user?.name || (isLocalDev ? 'Local Developer' : 'Guest')}
                            </span>
                            <span className="text-[10px] text-gray-500">
                                {session?.user?.email}
                            </span>
                        </div>
                        <button
                            onClick={() => signOut()}
                            className="relative group focus:outline-none"
                            title="Sign Out"
                        >
                            {session?.user?.image ? (
                                <div className="h-9 w-9 rounded-full overflow-hidden border border-gray-200 hover:shadow-md transition-shadow">
                                    <Image
                                        src={session.user.image}
                                        alt="Profile"
                                        width={36}
                                        height={36}
                                    />
                                </div>
                            ) : (
                                <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-medium hover:shadow-md transition-shadow">
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

            <div className="w-full max-w-3xl mt-20 space-y-10 text-center">
                <div className="space-y-6">
                    <div className="flex flex-col items-center justify-center">
                        <div className="relative w-20 h-20 mb-6">
                            <Image
                                src="/logo.svg"
                                alt="ReadPaper Logo"
                                fill
                                className="object-contain"
                                priority
                            />
                        </div>
                        <h1 className="text-5xl font-normal tracking-tight text-[#202124] mb-2">
                            ReadPaper
                        </h1>
                        <p className="text-lg text-[#5f6368]">
                            Bilingual arXiv reading experience powered by Gemini 3.0
                        </p>
                    </div>

                    <form onSubmit={handleTranslate} className="relative group flex flex-col items-center w-full max-w-2xl mx-auto space-y-6">
                        <div className="relative w-full">
                            <div className="absolute inset-y-0 left-0 flex items-center pl-5 pointer-events-none text-gray-400 group-focus-within:text-blue-500 transition-colors">
                                <Search size={20} />
                            </div>
                            <input
                                type="text"
                                placeholder="Paste arXiv URL (e.g., https://arxiv.org/abs/2602.04705)"
                                className="w-full py-3.5 pl-14 pr-4 text-[#202124] bg-white border border-[#dfe1e5] rounded-full hover:shadow-md focus:shadow-md outline-none transition-all text-base"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                disabled={loading}
                            />
                        </div>

                        <div className="flex gap-3">
                            <button
                                type="submit"
                                disabled={loading || !url}
                                className="bg-[#f8f9fa] hover:bg-[#f1f3f4] text-[#3c4043] border border-transparent hover:border-[#dadce0] font-medium px-6 py-2 rounded-md transition-all flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed min-w-[120px]"
                            >
                                {loading ? <Loader2 className="animate-spin mr-2" size={18} /> : null}
                                {loading ? 'Reading...' : 'Read Paper'}
                            </button>
                            <button
                                type="button"
                                onClick={() => setUrl('https://arxiv.org/abs/2403.05530')}
                                className="bg-[#f8f9fa] hover:bg-[#f1f3f4] text-[#3c4043] border border-transparent hover:border-[#dadce0] font-medium px-6 py-2 rounded-md transition-all min-w-[120px]"
                            >
                                I'm Feeling Lucky
                            </button>
                        </div>
                    </form>

                    {!session && !isLocalDev && (
                        <div className="mt-4 p-3 bg-blue-50 text-blue-700 rounded-lg text-sm">
                            <span className="font-semibold">Note:</span> You need to <button onClick={() => window.location.href = '/login'} className="underline font-bold hover:text-blue-800">sign in</button> to read papers and save them to your library.
                        </div>
                    )}

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
            </div>

            {/* Library Section */}
            <div className="w-full max-w-5xl px-4 py-16">
                <div className="flex flex-col md:flex-row justify-between items-baseline mb-8 gap-4 border-b border-gray-100 pb-4">
                    <h2 className="text-xl font-normal text-[#202124] flex items-center gap-3">
                        My Library
                        <span className="text-sm font-medium text-gray-500 bg-gray-100 px-2.5 py-0.5 rounded-full">
                            {library.length} papers
                        </span>
                    </h2>

                    {/* Library Search */}
                    <div className="relative w-full md:w-80">
                        <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-gray-400">
                            <Search size={16} />
                        </div>
                        <input
                            type="text"
                            placeholder="Search in library..."
                            className="w-full py-2 pl-10 pr-4 text-sm text-[#202124] bg-[#f1f3f4] border-transparent rounded-lg focus:bg-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
                            value={searchTerm}
                            onChange={(e) => {
                                setSearchTerm(e.target.value);
                                setCurrentPage(1);
                            }}
                        />
                    </div>
                </div>

                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-2">
                    {paginatedLibrary.map((paper: any) => (
                        <div
                            key={paper.id}
                            onClick={() => setArxivId(paper.id)}
                            className="bg-white p-6 rounded-xl border border-[#dadce0] hover:shadow-md hover:border-[#1a73e8] transition-all cursor-pointer group flex flex-col h-full relative"
                        >
                            <div className="flex justify-between items-start mb-3">
                                <span className="text-[11px] font-medium tracking-wider text-[#1a73e8] uppercase">
                                    arXiv:{paper.id}
                                </span>
                                <div className="flex items-center gap-3">
                                    <span className="text-[11px] text-gray-500">
                                        {new Date(paper.added_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                                    </span>
                                    <button
                                        onClick={(e) => deletePaper(e, paper.id)}
                                        className="text-gray-300 hover:text-red-600 transition-colors p-1 rounded-full hover:bg-red-50"
                                        title="Remove from library"
                                    >
                                        <Trash2 size={15} />
                                    </button>
                                </div>
                            </div>

                            <h3 className="text-lg font-medium text-[#202124] group-hover:text-[#1a73e8] transition-colors line-clamp-2 mb-3 leading-snug">
                                {paper.title || `arXiv:${paper.id}`}
                            </h3>

                            <p className="text-sm text-[#5f6368] line-clamp-3 mb-6 flex-1 leading-relaxed">
                                {paper.abstract || "No abstract available for this paper."}
                            </p>

                            <div className="flex items-center justify-between pt-4 border-t border-gray-50 mt-auto">
                                <div className="flex items-center gap-2 overflow-hidden mr-4">
                                    <User size={12} className="text-gray-400 flex-shrink-0" />
                                    <span className="text-[11px] text-[#5f6368] truncate font-medium">
                                        {(paper.authors || []).join(", ")}
                                    </span>
                                </div>
                                <div className="flex gap-1 flex-shrink-0">
                                    {(paper.categories || []).slice(0, 1).map((tag: string) => (
                                        <span key={tag} className="text-[10px] text-[#1a73e8] bg-blue-50 px-2 py-0.5 rounded font-medium">
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}

                    {library.length === 0 && (
                        <div className="col-span-2 text-center py-20 text-[#5f6368] bg-[#f8f9fa] rounded-2xl border border-dashed border-[#dadce0]">
                            <div className="flex flex-col items-center">
                                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center mb-4 shadow-sm text-gray-300">
                                    <Search size={24} />
                                </div>
                                <p className="text-base font-medium text-[#202124]">Your library is empty</p>
                                <p className="text-sm mt-1">Translate an arXiv paper to see it here.</p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Pagination Controls */}
                {totalPages > 1 && (
                    <div className="flex justify-center items-center gap-6 mt-12">
                        <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                            className="px-5 py-2 text-sm font-medium text-[#3c4043] bg-white border border-[#dadce0] rounded-full hover:bg-[#f8f9fa] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                        >
                            Previous
                        </button>
                        <span className="text-sm text-[#5f6368] font-medium">
                            {currentPage} / {totalPages}
                        </span>
                        <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                            className="px-5 py-2 text-sm font-medium text-[#3c4043] bg-white border border-[#dadce0] rounded-full hover:bg-[#f8f9fa] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                        >
                            Next
                        </button>
                    </div>
                )}
            </div>

            <div className="w-full max-w-5xl px-4 py-8">
                <TaskMonitor config={config} />
            </div>
        </div>
    );
}

function TaskMonitor({ config }: ClientHomeProps) {
    const [tasks, setTasks] = useState<any[]>([]);

    useEffect(() => {
        const fetchTasks = async () => {
            try {
                const res = await fetch(`${config.apiUrl}/tasks`);
                if (res.ok) {
                    const data = await res.json();
                    setTasks(data);
                }
            } catch (e) {
                console.error("Failed to fetch tasks", e);
            }
        };

        fetchTasks();
        const interval = setInterval(fetchTasks, 2000);
        return () => clearInterval(interval);
    }, [config.apiUrl]);

    if (tasks.length === 0) return null;

    return (
        <div className="bg-white rounded-xl border border-[#dadce0] overflow-hidden shadow-none">
            <div className="bg-[#f8f9fa] px-6 py-4 border-b border-[#dadce0] flex justify-between items-center">
                <h3 className="text-sm font-medium text-[#202124] flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin text-[#1a73e8]" />
                    Processing Tasks
                </h3>
                <span className="text-[11px] text-[#5f6368] font-medium uppercase tracking-wider">Live Status</span>
            </div>
            <div className="divide-y divide-[#dadce0]">
                {tasks.map((task) => (
                    <div key={task.arxiv_id} className="px-6 py-4 flex items-center justify-between hover:bg-[#f8f9fa] transition-colors">
                        <div className="flex-1 min-w-0 pr-8">
                            <div className="flex items-center gap-3 mb-1.5">
                                <span className="font-medium text-xs text-[#1a73e8] bg-blue-50 px-2 py-0.5 rounded">
                                    arXiv:{task.arxiv_id}
                                </span>
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-tighter ${task.status === 'completed' ? 'bg-green-50 text-green-700' :
                                    task.status === 'failed' ? 'bg-red-50 text-red-700' :
                                        'bg-blue-50 text-blue-700'
                                    }`}>
                                    {task.status}
                                </span>
                            </div>
                            <p className="text-sm text-[#202124] truncate font-normal">{task.message}</p>
                            {task.details && <p className="text-xs text-[#5f6368] mt-1 italic">{task.details}</p>}
                        </div>

                        {task.status === 'processing' && (
                            <div className="flex flex-col items-end gap-2 min-w-[120px]">
                                <span className="text-xs font-bold text-[#1a73e8]">{task.progress}%</span>
                                <div className="w-full h-1.5 bg-[#e8f0fe] rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-[#1a73e8] transition-all duration-700 ease-out"
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




