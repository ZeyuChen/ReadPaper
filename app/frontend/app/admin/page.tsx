'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
    Users, FileText, TrendingUp, RefreshCw,
    ChevronUp, ChevronDown, Search, ArrowLeft,
    Shield, BookOpen, Calendar, Zap, BarChart3,
    ExternalLink, Hash, Mail, Clock, Trash2,
    Code2, Terminal, Download, Copy, Check,
    AlertTriangle, Info, ChevronRight, Play, Pause,
    Eye
} from 'lucide-react';

const API_BASE = '/backend';
const ADMIN_EMAIL = 'chinachenzeyu@gmail.com';

// ── Types ────────────────────────────────────────────────────────────────────

interface AdminPaper {
    user_id: string;
    id: string;
    title?: string;
    authors?: string[];
    categories?: string[];
    abstract?: string;
    total_in_tokens: number;
    total_out_tokens: number;
    versions?: Array<{
        model: string;
        status: string;
        timestamp: string;
        total_in_tokens?: number;
        total_out_tokens?: number;
    }>;
}

interface AdminStats {
    total_users: number;
    total_papers: number;
    total_in_tokens: number;
    total_out_tokens: number;
    user_ids: string[];
}

interface AdminUser {
    user_id: string;
    email: string;
    paper_count: number;
    total_in_tokens: number;
    total_out_tokens: number;
}

interface DailyStat {
    date: string;
    papers_count: number;
    total_in_tokens: number;
    total_out_tokens: number;
}

interface TexFileList {
    original: string[];
    translated: string[];
}

interface LogEntry {
    timestamp: string;
    severity: string;
    message: string;
    trace: string;
}

type Tab = 'overview' | 'users' | 'papers' | 'analytics' | 'latex' | 'logs';
type SortKey = 'user_id' | 'id' | 'title' | 'total_in_tokens' | 'total_out_tokens';
type UserSortKey = 'email' | 'paper_count' | 'total_in_tokens' | 'total_out_tokens';
type SortDir = 'asc' | 'desc';

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTokens(n: number): string {
    if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
    return n.toString();
}

function emailToColor(email: string): string {
    let hash = 0;
    for (let i = 0; i < email.length; i++) hash = email.charCodeAt(i) + ((hash << 5) - hash);
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 55%, 50%)`;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function AdminPage() {
    const router = useRouter();

    // Auth guard
    const [authChecked, setAuthChecked] = useState(false);
    const [authorized, setAuthorized] = useState(false);

    // Data
    const [papers, setPapers] = useState<AdminPaper[]>([]);
    const [stats, setStats] = useState<AdminStats | null>(null);
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [dailyStats, setDailyStats] = useState<DailyStat[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // UI
    const [tab, setTab] = useState<Tab>('overview');
    const [search, setSearch] = useState('');
    const [paperSort, setPaperSort] = useState<{ key: SortKey; dir: SortDir }>({ key: 'user_id', dir: 'asc' });
    const [userSort, setUserSort] = useState<{ key: UserSortKey; dir: SortDir }>({ key: 'paper_count', dir: 'desc' });
    const [selectedUser, setSelectedUser] = useState<string>('all');

    // Date range for analytics
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

    // Canvas chart ref
    const chartRef = useRef<HTMLCanvasElement>(null);

    // Delete state
    const [deleting, setDeleting] = useState<string | null>(null); // track which item is being deleted

    // ── LaTeX Inspector state ──
    const [latexPaper, setLatexPaper] = useState<AdminPaper | null>(null);
    const [texFiles, setTexFiles] = useState<TexFileList | null>(null);
    const [texLoading, setTexLoading] = useState(false);
    const [selectedTexFile, setSelectedTexFile] = useState<string | null>(null);
    const [originalContent, setOriginalContent] = useState('');
    const [translatedContent, setTranslatedContent] = useState('');
    const [texContentLoading, setTexContentLoading] = useState(false);
    const [copiedField, setCopiedField] = useState<string | null>(null);
    const [latexSearch, setLatexSearch] = useState('');

    // ── GCP Logs state ──
    const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
    const [logService, setLogService] = useState<'backend' | 'frontend'>('backend');
    const [logSeverity, setLogSeverity] = useState('DEFAULT');
    const [logHours, setLogHours] = useState(1);
    const [logLimit, setLogLimit] = useState(100);
    const [logLoading, setLogLoading] = useState(false);
    const [logError, setLogError] = useState('');
    const [logAutoRefresh, setLogAutoRefresh] = useState(false);
    const logAutoRefreshRef = useRef<NodeJS.Timeout | null>(null);
    const [expandedLogIdx, setExpandedLogIdx] = useState<number | null>(null);

    // ── LaTeX Inspector handlers ──
    const loadTexFiles = useCallback(async (paper: AdminPaper) => {
        setLatexPaper(paper);
        setTexFiles(null);
        setSelectedTexFile(null);
        setOriginalContent('');
        setTranslatedContent('');
        setTexLoading(true);
        try {
            const res = await fetch(`${API_BASE}/admin/papers/${encodeURIComponent(paper.user_id)}/${encodeURIComponent(paper.id)}/texfiles`);
            if (!res.ok) throw new Error('Failed to load tex files');
            const data: TexFileList = await res.json();
            setTexFiles(data);
            // Auto-select first file
            const first = data.translated?.[0] || data.original?.[0];
            if (first) loadTexContent(paper, first);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setTexLoading(false);
        }
    }, []);

    const loadTexContent = useCallback(async (paper: AdminPaper, filename: string) => {
        setSelectedTexFile(filename);
        setTexContentLoading(true);
        setOriginalContent('');
        setTranslatedContent('');
        try {
            const [origRes, transRes] = await Promise.allSettled([
                fetch(`${API_BASE}/admin/papers/${encodeURIComponent(paper.user_id)}/${encodeURIComponent(paper.id)}/texfile?name=${encodeURIComponent(filename)}&type=original`),
                fetch(`${API_BASE}/admin/papers/${encodeURIComponent(paper.user_id)}/${encodeURIComponent(paper.id)}/texfile?name=${encodeURIComponent(filename)}&type=translated`),
            ]);
            if (origRes.status === 'fulfilled' && origRes.value.ok) {
                const d = await origRes.value.json();
                setOriginalContent(d.content || '');
            }
            if (transRes.status === 'fulfilled' && transRes.value.ok) {
                const d = await transRes.value.json();
                setTranslatedContent(d.content || '');
            }
        } catch { /* silent */ } finally {
            setTexContentLoading(false);
        }
    }, []);

    const copyToClipboard = useCallback(async (text: string, field: string) => {
        await navigator.clipboard.writeText(text);
        setCopiedField(field);
        setTimeout(() => setCopiedField(null), 2000);
    }, []);

    const downloadTexTar = useCallback((paper: AdminPaper) => {
        const url = `${API_BASE}/admin/papers/${encodeURIComponent(paper.user_id)}/${encodeURIComponent(paper.id)}/tex-tar`;
        const a = document.createElement('a');
        a.href = url;
        a.download = `${paper.id}_tex.tar.gz`;
        a.click();
    }, []);

    // ── GCP Logs handlers ──
    const fetchLogs = useCallback(async () => {
        setLogLoading(true);
        setLogError('');
        try {
            const res = await fetch(`${API_BASE}/admin/logs?service=${logService}&severity=${logSeverity}&limit=${logLimit}&hours=${logHours}`);
            if (!res.ok) throw new Error('Failed to fetch logs');
            const data = await res.json();
            if (data.error) setLogError(data.error);
            setLogEntries(data.entries || []);
        } catch (e: any) {
            setLogError(e.message);
            setLogEntries([]);
        } finally {
            setLogLoading(false);
        }
    }, [logService, logSeverity, logLimit, logHours]);

    // Auto-refresh for logs
    useEffect(() => {
        if (logAutoRefresh && tab === 'logs') {
            fetchLogs();
            logAutoRefreshRef.current = setInterval(fetchLogs, 30000);
        }
        return () => {
            if (logAutoRefreshRef.current) clearInterval(logAutoRefreshRef.current);
        };
    }, [logAutoRefresh, tab, fetchLogs]);

    // ── Auth check ──
    useEffect(() => {
        fetch(`${API_BASE}/admin/is-admin`)
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (d?.is_admin) {
                    setAuthorized(true);
                } else {
                    router.replace('/');
                }
                setAuthChecked(true);
            })
            .catch(() => {
                router.replace('/');
                setAuthChecked(true);
            });
    }, [router]);

    // ── Fetch all data ──
    const fetchData = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const headers: HeadersInit = { 'Content-Type': 'application/json' };
            const [papersRes, statsRes, usersRes, dailyRes] = await Promise.all([
                fetch(`${API_BASE}/admin/papers`, { headers }),
                fetch(`${API_BASE}/admin/stats`, { headers }),
                fetch(`${API_BASE}/admin/users`, { headers }),
                fetch(`${API_BASE}/admin/daily-stats`, { headers }),
            ]);
            if (!papersRes.ok || !statsRes.ok || !usersRes.ok || !dailyRes.ok) {
                throw new Error('Failed to load admin data');
            }
            setPapers(await papersRes.json());
            setStats(await statsRes.json());
            setUsers(await usersRes.json());
            setDailyStats(await dailyRes.json());
        } catch (e: any) {
            setError(e.message || 'Failed to load admin data');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (authorized) fetchData();
    }, [authorized, fetchData]);

    // ── Chart drawing ──
    const filteredDaily = dailyStats.filter(d => {
        if (dateFrom && d.date < dateFrom) return false;
        if (dateTo && d.date > dateTo) return false;
        return true;
    });

    useEffect(() => {
        if (tab !== 'analytics' || !chartRef.current || filteredDaily.length === 0) return;
        drawChart(chartRef.current, filteredDaily);
    }, [tab, filteredDaily, chartRef.current]);

    // ── Paper filtering / sorting ──
    const filteredPapers = papers
        .filter(p => selectedUser === 'all' || p.user_id === selectedUser)
        .filter(p => {
            const q = search.toLowerCase();
            return !q || p.id.includes(q) || (p.title ?? '').toLowerCase().includes(q) || p.user_id.toLowerCase().includes(q);
        })
        .sort((a, b) => {
            const key = paperSort.key;
            const av = key === 'total_in_tokens' || key === 'total_out_tokens' ? (a[key] ?? 0) : (a[key] ?? '').toString().toLowerCase();
            const bv = key === 'total_in_tokens' || key === 'total_out_tokens' ? (b[key] ?? 0) : (b[key] ?? '').toString().toLowerCase();
            if (typeof av === 'number' && typeof bv === 'number') {
                return paperSort.dir === 'asc' ? av - bv : bv - av;
            }
            return paperSort.dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        });

    // ── User filtering / sorting ──
    const filteredUsers = users
        .filter(u => {
            const q = search.toLowerCase();
            return !q || u.email.toLowerCase().includes(q);
        })
        .sort((a, b) => {
            const key = userSort.key;
            const av = key === 'email' ? a[key].toLowerCase() : a[key];
            const bv = key === 'email' ? b[key].toLowerCase() : b[key];
            if (typeof av === 'number' && typeof bv === 'number') {
                return userSort.dir === 'asc' ? av - bv : bv - av;
            }
            return userSort.dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        });

    const togglePaperSort = (key: SortKey) => {
        setPaperSort(prev => prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' });
    };

    const toggleUserSort = (key: UserSortKey) => {
        setUserSort(prev => prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' });
    };

    // ── Delete handlers ──
    const handleDeletePaper = async (userId: string, arxivId: string, title?: string) => {
        const label = title ? `"${title}" (${arxivId})` : arxivId;
        if (!window.confirm(`Delete paper ${label} for user ${userId}?\n\nThis will permanently remove:\n• GCS storage files\n• Library entry\n• Status cache`)) return;
        const key = `${userId}:${arxivId}`;
        setDeleting(key);
        try {
            const res = await fetch(`${API_BASE}/admin/papers/${encodeURIComponent(userId)}/${encodeURIComponent(arxivId)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json()).detail || 'Delete failed');
            await fetchData();
        } catch (e: any) {
            alert(`Failed to delete paper: ${e.message}`);
        } finally {
            setDeleting(null);
        }
    };

    const handleDeleteUser = async (userId: string, paperCount: number) => {
        if (!window.confirm(`Delete ALL data for user "${userId}"?\n\n⚠️ This will permanently remove:\n• ${paperCount} paper(s) and their GCS files\n• Library data\n• All status caches\n\nThis action cannot be undone!`)) return;
        setDeleting(`user:${userId}`);
        try {
            const res = await fetch(`${API_BASE}/admin/users/${encodeURIComponent(userId)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json()).detail || 'Delete failed');
            await fetchData();
        } catch (e: any) {
            alert(`Failed to delete user: ${e.message}`);
        } finally {
            setDeleting(null);
        }
    };

    const SortIcon = ({ active, dir }: { active: boolean; dir: SortDir }) =>
        active ? (dir === 'asc' ? <ChevronUp size={12} className="inline ml-0.5" /> : <ChevronDown size={12} className="inline ml-0.5" />) : null;

    // ── Loading / unauthorized ──
    if (!authChecked) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f8f9fa]">
                <RefreshCw size={24} className="animate-spin text-blue-500" />
            </div>
        );
    }
    if (!authorized) return null;

    // ── Analytics summary for selected range ──
    const analyticsSummary = {
        totalPapers: filteredDaily.reduce((s, d) => s + d.papers_count, 0),
        totalTokens: filteredDaily.reduce((s, d) => s + d.total_in_tokens + d.total_out_tokens, 0),
        avgPapersPerDay: filteredDaily.length > 0 ? (filteredDaily.reduce((s, d) => s + d.papers_count, 0) / filteredDaily.length).toFixed(1) : '0',
        days: filteredDaily.length,
    };

    const userList = stats?.user_ids ?? [];

    // ── Tabs config ──
    const tabs: { id: Tab; label: string; icon: any }[] = [
        { id: 'overview', label: 'Overview', icon: BarChart3 },
        { id: 'users', label: 'Users', icon: Users },
        { id: 'papers', label: 'Papers', icon: FileText },
        { id: 'analytics', label: 'Analytics', icon: TrendingUp },
        { id: 'latex', label: 'LaTeX Inspector', icon: Code2 },
        { id: 'logs', label: 'GCP Logs', icon: Terminal },
    ];

    return (
        <div className="min-h-screen bg-[#f8f9fa] font-sans">
            {/* Header */}
            <div className="bg-white border-b border-[#dadce0] px-6 py-3 flex items-center gap-3 sticky top-0 z-10 shadow-sm">
                <button onClick={() => router.push('/')} className="p-1.5 text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition">
                    <ArrowLeft size={18} />
                </button>
                <div className="flex items-center gap-2">
                    <Shield size={20} className="text-[#1a73e8]" />
                    <h1 className="text-base font-semibold text-[#202124]">Admin Dashboard</h1>
                </div>
                <span className="text-xs text-[#9aa0a6] ml-1">ReadPaper</span>
                <div className="flex-1" />
                <button
                    onClick={fetchData}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition disabled:opacity-50"
                >
                    <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
                </button>
                <span className="text-xs text-[#9aa0a6] bg-blue-50 px-2 py-0.5 rounded-full font-mono flex items-center gap-1">
                    <Shield size={10} className="text-blue-500" /> {ADMIN_EMAIL.split('@')[0]}
                </span>
            </div>

            {/* Tab bar */}
            <div className="bg-white border-b border-[#dadce0] px-6">
                <div className="max-w-7xl mx-auto flex gap-1">
                    {tabs.map(t => {
                        const Icon = t.icon;
                        const active = tab === t.id;
                        return (
                            <button
                                key={t.id}
                                onClick={() => setTab(t.id)}
                                className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${active
                                    ? 'border-[#1a73e8] text-[#1a73e8]'
                                    : 'border-transparent text-[#5f6368] hover:text-[#202124] hover:bg-[#f8f9fa]'
                                    }`}
                            >
                                <Icon size={15} />
                                {t.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
                        ⚠ {error}
                    </div>
                )}

                {/* ═══ OVERVIEW TAB ═══ */}
                {tab === 'overview' && stats && (
                    <>
                        {/* Stats Cards */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard icon={Users} color="blue" label="Total Users" value={stats.total_users} />
                            <StatCard icon={BookOpen} color="green" label="Papers Translated" value={stats.total_papers} />
                            <StatCard icon={Zap} color="purple" label="Total Tokens" value={fmtTokens(stats.total_in_tokens + stats.total_out_tokens)} sub={`In: ${fmtTokens(stats.total_in_tokens)} / Out: ${fmtTokens(stats.total_out_tokens)}`} />
                            <StatCard icon={TrendingUp} color="amber" label="Papers / User" value={stats.total_users > 0 ? (stats.total_papers / stats.total_users).toFixed(1) : '—'} />
                        </div>

                        {/* Quick tables preview */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            {/* Recent users */}
                            <div className="bg-white rounded-xl border border-[#dadce0] shadow-sm overflow-hidden">
                                <div className="px-5 py-3 border-b border-[#f1f3f4] flex items-center justify-between">
                                    <h3 className="text-sm font-semibold text-[#202124] flex items-center gap-2">
                                        <Users size={15} className="text-blue-500" /> Users
                                    </h3>
                                    <button onClick={() => setTab('users')} className="text-xs text-[#1a73e8] hover:underline">View all →</button>
                                </div>
                                <div className="divide-y divide-[#f1f3f4]">
                                    {users.slice(0, 5).map(u => (
                                        <div key={u.user_id} className="px-5 py-3 flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0" style={{ backgroundColor: emailToColor(u.email) }}>
                                                {u.email.charAt(0).toUpperCase()}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <p className="text-xs font-medium text-[#202124] truncate">{u.email}</p>
                                                <p className="text-[10px] text-[#9aa0a6]">{u.paper_count} papers · {fmtTokens(u.total_in_tokens + u.total_out_tokens)} tokens</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Recent papers */}
                            <div className="bg-white rounded-xl border border-[#dadce0] shadow-sm overflow-hidden">
                                <div className="px-5 py-3 border-b border-[#f1f3f4] flex items-center justify-between">
                                    <h3 className="text-sm font-semibold text-[#202124] flex items-center gap-2">
                                        <FileText size={15} className="text-green-500" /> Recent Papers
                                    </h3>
                                    <button onClick={() => setTab('papers')} className="text-xs text-[#1a73e8] hover:underline">View all →</button>
                                </div>
                                <div className="divide-y divide-[#f1f3f4]">
                                    {papers.slice(0, 5).map(p => (
                                        <div key={`${p.user_id}-${p.id}`} className="px-5 py-3">
                                            <div className="flex items-center gap-2 mb-0.5">
                                                <a href={`https://arxiv.org/abs/${p.id}`} target="_blank" rel="noopener noreferrer" className="text-xs font-mono text-[#1a73e8] hover:underline">{p.id}</a>
                                                <span className="text-[10px] text-[#9aa0a6] bg-[#f1f3f4] px-1.5 py-0.5 rounded-full">{p.user_id.split('@')[0]}</span>
                                            </div>
                                            <p className="text-xs text-[#202124] line-clamp-1">{p.title || <span className="text-[#9aa0a6] italic">No title</span>}</p>
                                            {(p.total_in_tokens > 0 || p.total_out_tokens > 0) && (
                                                <p className="text-[10px] text-purple-500 mt-0.5">🔤 {fmtTokens(p.total_in_tokens + p.total_out_tokens)} tokens</p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </>
                )}

                {/* ═══ USERS TAB ═══ */}
                {tab === 'users' && (
                    <>
                        <div className="flex gap-3 items-center">
                            <div className="relative flex-1 max-w-md">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa0a6]" />
                                <input
                                    type="text"
                                    placeholder="Search users by email..."
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    className="w-full pl-8 pr-4 py-2 text-sm border border-[#dadce0] rounded-full bg-white focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8] outline-none transition"
                                />
                            </div>
                            <span className="text-xs text-[#9aa0a6]">{filteredUsers.length} user{filteredUsers.length !== 1 ? 's' : ''}</span>
                        </div>

                        <div className="bg-white rounded-xl border border-[#dadce0] overflow-hidden shadow-sm">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-[#dadce0] bg-[#f8f9fa]">
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider w-12">#</th>
                                        <ThSortable label="Email" sortKey="email" current={userSort} onSort={toggleUserSort} />
                                        <ThSortable label="Papers" sortKey="paper_count" current={userSort} onSort={toggleUserSort} />
                                        <ThSortable label="Input Tokens" sortKey="total_in_tokens" current={userSort} onSort={toggleUserSort} />
                                        <ThSortable label="Output Tokens" sortKey="total_out_tokens" current={userSort} onSort={toggleUserSort} />
                                        <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Total Tokens</th>
                                        <th className="px-4 py-3 text-center text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider w-20">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading && (
                                        <tr><td colSpan={7} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">
                                            <RefreshCw size={18} className="animate-spin inline mr-2 text-blue-400" />Loading...
                                        </td></tr>
                                    )}
                                    {!loading && filteredUsers.length === 0 && (
                                        <tr><td colSpan={7} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">No users found</td></tr>
                                    )}
                                    {!loading && filteredUsers.map((u, i) => (
                                        <tr key={u.user_id} className={`border-b border-[#f1f3f4] hover:bg-[#f8f9fa] transition-colors ${i % 2 === 0 ? '' : 'bg-[#fafafa]'}`}>
                                            <td className="px-4 py-3 text-xs text-[#9aa0a6]">{i + 1}</td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2.5">
                                                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0" style={{ backgroundColor: emailToColor(u.email) }}>
                                                        {u.email.charAt(0).toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <p className="text-xs font-medium text-[#202124]">{u.email}</p>
                                                        <p className="text-[10px] text-[#9aa0a6]">ID: {u.user_id}</p>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className="text-xs font-semibold text-[#202124] bg-blue-50 px-2 py-0.5 rounded-full">{u.paper_count}</span>
                                            </td>
                                            <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{u.total_in_tokens.toLocaleString()}</td>
                                            <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{u.total_out_tokens.toLocaleString()}</td>
                                            <td className="px-4 py-3">
                                                <span className="text-xs font-semibold text-purple-600 font-mono tabular-nums">
                                                    {fmtTokens(u.total_in_tokens + u.total_out_tokens)}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <button
                                                    onClick={() => handleDeleteUser(u.user_id, u.paper_count)}
                                                    disabled={deleting === `user:${u.user_id}`}
                                                    className="p-1.5 text-[#9aa0a6] hover:text-red-500 hover:bg-red-50 rounded-full transition-colors disabled:opacity-50"
                                                    title={`Delete all data for ${u.email}`}
                                                >
                                                    {deleting === `user:${u.user_id}` ? (
                                                        <RefreshCw size={13} className="animate-spin" />
                                                    ) : (
                                                        <Trash2 size={13} />
                                                    )}
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </>
                )}

                {/* ═══ PAPERS TAB ═══ */}
                {tab === 'papers' && (
                    <>
                        <div className="flex gap-3 items-center flex-wrap">
                            <div className="relative flex-1 max-w-md">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa0a6]" />
                                <input
                                    type="text"
                                    placeholder="Search by user, paper ID, or title..."
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    className="w-full pl-8 pr-4 py-2 text-sm border border-[#dadce0] rounded-full bg-white focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8] outline-none transition"
                                />
                            </div>
                            <select
                                value={selectedUser}
                                onChange={e => setSelectedUser(e.target.value)}
                                className="px-3 py-2 text-sm border border-[#dadce0] rounded-full bg-white text-[#5f6368] outline-none focus:border-[#1a73e8] cursor-pointer"
                            >
                                <option value="all">All Users ({userList.length})</option>
                                {userList.map(uid => (
                                    <option key={uid} value={uid}>{uid}</option>
                                ))}
                            </select>
                            <span className="text-xs text-[#9aa0a6]">{filteredPapers.length} paper{filteredPapers.length !== 1 ? 's' : ''}</span>
                        </div>

                        <div className="bg-white rounded-xl border border-[#dadce0] overflow-hidden shadow-sm">
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-[#dadce0] bg-[#f8f9fa]">
                                            <ThSortable label="User" sortKey="user_id" current={paperSort} onSort={togglePaperSort} />
                                            <ThSortable label="Paper ID" sortKey="id" current={paperSort} onSort={togglePaperSort} />
                                            <ThSortable label="Title" sortKey="title" current={paperSort} onSort={togglePaperSort} />
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Authors</th>
                                            <ThSortable label="In Tokens" sortKey="total_in_tokens" current={paperSort} onSort={togglePaperSort} />
                                            <ThSortable label="Out Tokens" sortKey="total_out_tokens" current={paperSort} onSort={togglePaperSort} />
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Versions</th>
                                            <th className="px-4 py-3 text-center text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider w-16"></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {loading && (
                                            <tr><td colSpan={8} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">
                                                <RefreshCw size={18} className="animate-spin inline mr-2 text-blue-400" />Loading...
                                            </td></tr>
                                        )}
                                        {!loading && filteredPapers.length === 0 && (
                                            <tr><td colSpan={8} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">No papers found</td></tr>
                                        )}
                                        {!loading && filteredPapers.map((p, i) => (
                                            <tr key={`${p.user_id}-${p.id}`} className={`border-b border-[#f1f3f4] hover:bg-[#f8f9fa] transition-colors ${i % 2 === 0 ? '' : 'bg-[#fafafa]'}`}>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-6 h-6 rounded-full flex items-center justify-center text-white text-[9px] font-bold flex-shrink-0" style={{ backgroundColor: emailToColor(p.user_id) }}>
                                                            {p.user_id.charAt(0).toUpperCase()}
                                                        </div>
                                                        <span className="text-[11px] font-mono text-[#5f6368] truncate max-w-[140px]">{p.user_id}</span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <a href={`https://arxiv.org/abs/${p.id}`} target="_blank" rel="noopener noreferrer" className="text-[#1a73e8] hover:underline font-mono text-xs flex items-center gap-1">
                                                        {p.id} <ExternalLink size={10} />
                                                    </a>
                                                </td>
                                                <td className="px-4 py-3 max-w-xs">
                                                    <div className="text-xs text-[#202124] leading-snug line-clamp-2">
                                                        {p.title || <span className="text-[#9aa0a6] italic">No title</span>}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 max-w-[140px]">
                                                    <div className="text-[11px] text-[#5f6368] line-clamp-1">
                                                        {p.authors?.slice(0, 3).join(', ')}{(p.authors?.length ?? 0) > 3 && ` +${(p.authors?.length ?? 0) - 3}`}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{p.total_in_tokens.toLocaleString()}</td>
                                                <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{p.total_out_tokens.toLocaleString()}</td>
                                                <td className="px-4 py-3">
                                                    <div className="flex flex-wrap gap-1">
                                                        {p.versions?.map(v => (
                                                            <span key={v.model} className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${v.status === 'completed' ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
                                                                {v.model} · {v.status}
                                                            </span>
                                                        ))}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-center">
                                                    <button
                                                        onClick={() => handleDeletePaper(p.user_id, p.id, p.title)}
                                                        disabled={deleting === `${p.user_id}:${p.id}`}
                                                        className="p-1.5 text-[#9aa0a6] hover:text-red-500 hover:bg-red-50 rounded-full transition-colors disabled:opacity-50"
                                                        title={`Delete paper ${p.id}`}
                                                    >
                                                        {deleting === `${p.user_id}:${p.id}` ? (
                                                            <RefreshCw size={13} className="animate-spin" />
                                                        ) : (
                                                            <Trash2 size={13} />
                                                        )}
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </>
                )}

                {/* ═══ ANALYTICS TAB ═══ */}
                {tab === 'analytics' && (
                    <>
                        {/* Date range picker */}
                        <div className="flex flex-wrap gap-3 items-center">
                            <div className="flex items-center gap-2 text-sm text-[#5f6368]">
                                <Calendar size={14} />
                                <span className="text-xs font-medium">Date Range:</span>
                            </div>
                            <input
                                type="date"
                                value={dateFrom}
                                onChange={e => setDateFrom(e.target.value)}
                                className="px-3 py-1.5 text-xs border border-[#dadce0] rounded-lg bg-white text-[#202124] outline-none focus:border-[#1a73e8]"
                            />
                            <span className="text-xs text-[#9aa0a6]">to</span>
                            <input
                                type="date"
                                value={dateTo}
                                onChange={e => setDateTo(e.target.value)}
                                className="px-3 py-1.5 text-xs border border-[#dadce0] rounded-lg bg-white text-[#202124] outline-none focus:border-[#1a73e8]"
                            />
                            {(dateFrom || dateTo) && (
                                <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-xs text-[#1a73e8] hover:underline">Clear</button>
                            )}
                        </div>

                        {/* Summary cards for selected range */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard icon={Calendar} color="blue" label="Days in Range" value={analyticsSummary.days} />
                            <StatCard icon={BookOpen} color="green" label="Papers (Range)" value={analyticsSummary.totalPapers} />
                            <StatCard icon={Zap} color="purple" label="Tokens (Range)" value={fmtTokens(analyticsSummary.totalTokens)} />
                            <StatCard icon={TrendingUp} color="amber" label="Avg Papers/Day" value={analyticsSummary.avgPapersPerDay} />
                        </div>

                        {/* Chart */}
                        <div className="bg-white rounded-xl border border-[#dadce0] shadow-sm p-6">
                            <h3 className="text-sm font-semibold text-[#202124] mb-4 flex items-center gap-2">
                                <BarChart3 size={16} className="text-[#1a73e8]" />
                                Daily Translations & Token Usage
                            </h3>
                            {filteredDaily.length === 0 ? (
                                <div className="text-center py-16 text-[#9aa0a6] text-sm">
                                    No data for the selected date range
                                </div>
                            ) : (
                                <div className="relative">
                                    <canvas ref={chartRef} height={320} className="w-full" />
                                    {/* Legend */}
                                    <div className="flex justify-center gap-6 mt-4">
                                        <div className="flex items-center gap-1.5">
                                            <div className="w-3 h-3 rounded-full bg-[#1a73e8]" />
                                            <span className="text-xs text-[#5f6368]">Papers Translated</span>
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <div className="w-3 h-3 rounded-full bg-[#e8710a]" />
                                            <span className="text-xs text-[#5f6368]">Token Usage</span>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Daily stats table */}
                        <div className="bg-white rounded-xl border border-[#dadce0] overflow-hidden shadow-sm">
                            <div className="px-5 py-3 border-b border-[#f1f3f4]">
                                <h3 className="text-sm font-semibold text-[#202124] flex items-center gap-2">
                                    <Clock size={15} className="text-[#5f6368]" /> Daily Breakdown
                                </h3>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-[#dadce0] bg-[#f8f9fa]">
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Date</th>
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Papers</th>
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Input Tokens</th>
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Output Tokens</th>
                                            <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">Total Tokens</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredDaily.slice().reverse().map((d, i) => (
                                            <tr key={d.date} className={`border-b border-[#f1f3f4] hover:bg-[#f8f9fa] transition-colors ${i % 2 === 0 ? '' : 'bg-[#fafafa]'}`}>
                                                <td className="px-4 py-3">
                                                    <span className="text-xs font-mono text-[#202124] bg-[#f1f3f4] px-2 py-0.5 rounded">{d.date}</span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <span className="text-xs font-semibold text-[#202124] bg-blue-50 px-2 py-0.5 rounded-full">{d.papers_count}</span>
                                                </td>
                                                <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{d.total_in_tokens.toLocaleString()}</td>
                                                <td className="px-4 py-3 text-xs text-[#5f6368] font-mono tabular-nums">{d.total_out_tokens.toLocaleString()}</td>
                                                <td className="px-4 py-3">
                                                    <span className="text-xs font-semibold text-purple-600 font-mono tabular-nums">
                                                        {fmtTokens(d.total_in_tokens + d.total_out_tokens)}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </>
                )}

                {/* ═══ LATEX INSPECTOR TAB ═══ */}
                {tab === 'latex' && (
                    <>
                        {/* Paper selector */}
                        <div className="flex gap-3 items-center flex-wrap">
                            <div className="relative flex-1 max-w-md">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa0a6]" />
                                <input
                                    type="text"
                                    placeholder="Search papers to inspect..."
                                    value={latexSearch}
                                    onChange={e => setLatexSearch(e.target.value)}
                                    className="w-full pl-8 pr-4 py-2 text-sm border border-[#dadce0] rounded-full bg-white focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8] outline-none transition"
                                />
                            </div>
                            <span className="text-xs text-[#9aa0a6]">
                                {papers.filter(p => {
                                    const q = latexSearch.toLowerCase();
                                    return !q || p.id.includes(q) || (p.title ?? '').toLowerCase().includes(q) || p.user_id.toLowerCase().includes(q);
                                }).length} papers
                            </span>
                        </div>

                        {/* Paper cards grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {papers
                                .filter(p => {
                                    const q = latexSearch.toLowerCase();
                                    return !q || p.id.includes(q) || (p.title ?? '').toLowerCase().includes(q) || p.user_id.toLowerCase().includes(q);
                                })
                                .slice(0, 30)
                                .map(p => {
                                    const isSelected = latexPaper?.id === p.id && latexPaper?.user_id === p.user_id;
                                    const latestVersion = p.versions?.[p.versions.length - 1];
                                    return (
                                        <button
                                            key={`${p.user_id}-${p.id}`}
                                            onClick={() => loadTexFiles(p)}
                                            className={`text-left p-4 rounded-xl border transition-all ${isSelected
                                                    ? 'border-[#1a73e8] bg-blue-50 shadow-md ring-1 ring-[#1a73e8]/30'
                                                    : 'border-[#dadce0] bg-white hover:border-[#9aa0a6] hover:shadow-sm'
                                                }`}
                                        >
                                            <div className="flex items-center gap-2 mb-1.5">
                                                <span className="text-xs font-mono text-[#1a73e8] font-medium">{p.id}</span>
                                                {latestVersion && (
                                                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${latestVersion.status === 'completed'
                                                            ? 'bg-green-100 text-green-700'
                                                            : 'bg-yellow-100 text-yellow-700'
                                                        }`}>
                                                        {latestVersion.status}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-[#202124] line-clamp-2 mb-1.5">
                                                {p.title || <span className="text-[#9aa0a6] italic">No title</span>}
                                            </p>
                                            <p className="text-[10px] text-[#9aa0a6] truncate">{p.user_id}</p>
                                        </button>
                                    );
                                })}
                        </div>

                        {/* Selected paper detail */}
                        {latexPaper && (
                            <div className="bg-white rounded-xl border border-[#dadce0] shadow-sm overflow-hidden">
                                {/* Paper header */}
                                <div className="px-5 py-3 border-b border-[#f1f3f4] flex items-center justify-between flex-wrap gap-2">
                                    <div className="flex items-center gap-3">
                                        <Code2 size={16} className="text-[#1a73e8]" />
                                        <div>
                                            <h3 className="text-sm font-semibold text-[#202124]">{latexPaper.id}</h3>
                                            <p className="text-[10px] text-[#9aa0a6] truncate max-w-xs">{latexPaper.title}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => downloadTexTar(latexPaper)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#1a73e8] text-white rounded-full hover:bg-[#1765cc] transition-colors"
                                        >
                                            <Download size={12} /> Download .tar.gz
                                        </button>
                                        <a
                                            href={`https://arxiv.org/abs/${latexPaper.id}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-1 px-3 py-1.5 text-xs text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition"
                                        >
                                            arXiv <ExternalLink size={10} />
                                        </a>
                                    </div>
                                </div>

                                {texLoading && (
                                    <div className="flex items-center justify-center py-12">
                                        <RefreshCw size={18} className="animate-spin text-blue-400 mr-2" />
                                        <span className="text-xs text-[#9aa0a6]">Loading files...</span>
                                    </div>
                                )}

                                {texFiles && !texLoading && (
                                    <div className="flex" style={{ minHeight: 500 }}>
                                        {/* File tree sidebar */}
                                        <div className="w-56 flex-shrink-0 border-r border-[#f1f3f4] bg-[#fafafa] overflow-y-auto">
                                            <div className="px-3 py-2 text-[10px] font-semibold text-[#5f6368] uppercase tracking-wider">Files</div>
                                            {(() => {
                                                const allFiles = Array.from(new Set([...texFiles.original, ...texFiles.translated]));
                                                return allFiles.map(f => {
                                                    const hasOrig = texFiles.original.includes(f);
                                                    const hasTrans = texFiles.translated.includes(f);
                                                    const isActive = selectedTexFile === f;
                                                    return (
                                                        <button
                                                            key={f}
                                                            onClick={() => loadTexContent(latexPaper, f)}
                                                            className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 transition-colors ${isActive
                                                                    ? 'bg-blue-50 text-[#1a73e8] border-r-2 border-[#1a73e8]'
                                                                    : 'text-[#5f6368] hover:bg-[#f1f3f4]'
                                                                }`}
                                                        >
                                                            <FileText size={12} className={isActive ? 'text-[#1a73e8]' : 'text-[#9aa0a6]'} />
                                                            <span className="truncate flex-1 font-mono text-[11px]">{f}</span>
                                                            <div className="flex gap-0.5">
                                                                {hasOrig && <span className="w-1.5 h-1.5 rounded-full bg-gray-400" title="Original" />}
                                                                {hasTrans && <span className="w-1.5 h-1.5 rounded-full bg-green-500" title="Translated" />}
                                                            </div>
                                                        </button>
                                                    );
                                                });
                                            })()}
                                            {texFiles.original.length === 0 && texFiles.translated.length === 0 && (
                                                <div className="px-3 py-6 text-center text-xs text-[#9aa0a6]">No .tex files found</div>
                                            )}
                                        </div>

                                        {/* Side-by-side content */}
                                        <div className="flex-1 flex min-w-0">
                                            {texContentLoading ? (
                                                <div className="flex-1 flex items-center justify-center">
                                                    <RefreshCw size={18} className="animate-spin text-blue-400 mr-2" />
                                                    <span className="text-xs text-[#9aa0a6]">Loading content...</span>
                                                </div>
                                            ) : selectedTexFile ? (
                                                <>
                                                    {/* Original panel */}
                                                    <div className="flex-1 flex flex-col border-r border-[#f1f3f4] min-w-0">
                                                        <div className="px-3 py-2 border-b border-[#f1f3f4] bg-[#f8f9fa] flex items-center justify-between">
                                                            <span className="text-[10px] font-semibold text-[#5f6368] uppercase tracking-wider flex items-center gap-1.5">
                                                                <span className="w-2 h-2 rounded-full bg-gray-400" /> Original
                                                            </span>
                                                            {originalContent && (
                                                                <button
                                                                    onClick={() => copyToClipboard(originalContent, 'orig')}
                                                                    className="p-1 text-[#9aa0a6] hover:text-[#202124] transition-colors"
                                                                    title="Copy"
                                                                >
                                                                    {copiedField === 'orig' ? <Check size={12} className="text-green-500" /> : <Copy size={12} />}
                                                                </button>
                                                            )}
                                                        </div>
                                                        <div className="flex-1 overflow-auto">
                                                            {originalContent ? (
                                                                <pre className="text-[11px] font-mono text-[#202124] p-3 leading-5 whitespace-pre-wrap break-words">
                                                                    {originalContent.split('\n').map((line, i) => (
                                                                        <div key={i} className="flex hover:bg-yellow-50/50">
                                                                            <span className="text-[#9aa0a6] select-none w-10 text-right pr-3 flex-shrink-0 tabular-nums">{i + 1}</span>
                                                                            <span className="flex-1">{line || ' '}</span>
                                                                        </div>
                                                                    ))}
                                                                </pre>
                                                            ) : (
                                                                <div className="flex-1 flex items-center justify-center text-xs text-[#9aa0a6] py-12">
                                                                    No original file
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>

                                                    {/* Translated panel */}
                                                    <div className="flex-1 flex flex-col min-w-0">
                                                        <div className="px-3 py-2 border-b border-[#f1f3f4] bg-[#f8f9fa] flex items-center justify-between">
                                                            <span className="text-[10px] font-semibold text-[#5f6368] uppercase tracking-wider flex items-center gap-1.5">
                                                                <span className="w-2 h-2 rounded-full bg-green-500" /> Translated
                                                            </span>
                                                            {translatedContent && (
                                                                <button
                                                                    onClick={() => copyToClipboard(translatedContent, 'trans')}
                                                                    className="p-1 text-[#9aa0a6] hover:text-[#202124] transition-colors"
                                                                    title="Copy"
                                                                >
                                                                    {copiedField === 'trans' ? <Check size={12} className="text-green-500" /> : <Copy size={12} />}
                                                                </button>
                                                            )}
                                                        </div>
                                                        <div className="flex-1 overflow-auto">
                                                            {translatedContent ? (
                                                                <pre className="text-[11px] font-mono text-[#202124] p-3 leading-5 whitespace-pre-wrap break-words">
                                                                    {translatedContent.split('\n').map((line, i) => (
                                                                        <div key={i} className="flex hover:bg-green-50/50">
                                                                            <span className="text-[#9aa0a6] select-none w-10 text-right pr-3 flex-shrink-0 tabular-nums">{i + 1}</span>
                                                                            <span className="flex-1">{line || ' '}</span>
                                                                        </div>
                                                                    ))}
                                                                </pre>
                                                            ) : (
                                                                <div className="flex-1 flex items-center justify-center text-xs text-[#9aa0a6] py-12">
                                                                    No translated file
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </>
                                            ) : (
                                                <div className="flex-1 flex items-center justify-center text-xs text-[#9aa0a6]">
                                                    Select a file from the sidebar
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {!latexPaper && (
                            <div className="bg-white rounded-xl border border-[#dadce0] shadow-sm p-12 text-center">
                                <Code2 size={32} className="mx-auto text-[#dadce0] mb-3" />
                                <p className="text-sm text-[#5f6368]">Select a paper above to inspect its LaTeX source files</p>
                                <p className="text-xs text-[#9aa0a6] mt-1">Compare original vs translated side-by-side</p>
                            </div>
                        )}
                    </>
                )}

                {/* ═══ GCP LOGS TAB ═══ */}
                {tab === 'logs' && (
                    <>
                        {/* Controls bar */}
                        <div className="flex flex-wrap gap-3 items-center">
                            {/* Service toggle */}
                            <div className="flex rounded-full bg-[#f1f3f4] p-0.5">
                                {(['backend', 'frontend'] as const).map(svc => (
                                    <button
                                        key={svc}
                                        onClick={() => setLogService(svc)}
                                        className={`px-3 py-1.5 text-xs font-medium rounded-full transition-all ${logService === svc
                                                ? 'bg-white text-[#202124] shadow-sm'
                                                : 'text-[#5f6368] hover:text-[#202124]'
                                            }`}
                                    >
                                        {svc}
                                    </button>
                                ))}
                            </div>

                            {/* Severity filter */}
                            <select
                                value={logSeverity}
                                onChange={e => setLogSeverity(e.target.value)}
                                className="px-3 py-1.5 text-xs border border-[#dadce0] rounded-full bg-white text-[#5f6368] outline-none focus:border-[#1a73e8] cursor-pointer"
                            >
                                <option value="DEFAULT">All Severities</option>
                                <option value="ERROR">≥ ERROR</option>
                                <option value="WARNING">≥ WARNING</option>
                                <option value="INFO">≥ INFO</option>
                            </select>

                            {/* Time range */}
                            <select
                                value={logHours}
                                onChange={e => setLogHours(Number(e.target.value))}
                                className="px-3 py-1.5 text-xs border border-[#dadce0] rounded-full bg-white text-[#5f6368] outline-none focus:border-[#1a73e8] cursor-pointer"
                            >
                                <option value={1}>Last 1 hour</option>
                                <option value={6}>Last 6 hours</option>
                                <option value={24}>Last 24 hours</option>
                                <option value={168}>Last 7 days</option>
                            </select>

                            {/* Limit */}
                            <select
                                value={logLimit}
                                onChange={e => setLogLimit(Number(e.target.value))}
                                className="px-3 py-1.5 text-xs border border-[#dadce0] rounded-full bg-white text-[#5f6368] outline-none focus:border-[#1a73e8] cursor-pointer"
                            >
                                <option value={50}>50 entries</option>
                                <option value={100}>100 entries</option>
                                <option value={200}>200 entries</option>
                                <option value={500}>500 entries</option>
                            </select>

                            {/* Auto-refresh toggle */}
                            <button
                                onClick={() => setLogAutoRefresh(prev => !prev)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full transition-all ${logAutoRefresh
                                        ? 'bg-green-100 text-green-700 border border-green-200'
                                        : 'text-[#5f6368] hover:bg-[#f1f3f4] border border-[#dadce0]'
                                    }`}
                            >
                                {logAutoRefresh ? <Pause size={11} /> : <Play size={11} />}
                                {logAutoRefresh ? 'Auto (30s)' : 'Auto-refresh'}
                            </button>

                            {/* Fetch button */}
                            <button
                                onClick={fetchLogs}
                                disabled={logLoading}
                                className="flex items-center gap-1.5 px-4 py-1.5 text-xs bg-[#1a73e8] text-white rounded-full hover:bg-[#1765cc] transition-colors disabled:opacity-50"
                            >
                                <RefreshCw size={11} className={logLoading ? 'animate-spin' : ''} />
                                {logLoading ? 'Loading...' : 'Fetch Logs'}
                            </button>
                        </div>

                        {/* Error/Info messages */}
                        {logError && (
                            <div className="bg-amber-50 border border-amber-200 text-amber-700 text-xs px-4 py-2.5 rounded-lg flex items-center gap-2">
                                <AlertTriangle size={13} />
                                {logError}
                            </div>
                        )}

                        {/* Stats summary */}
                        {logEntries.length > 0 && (
                            <div className="flex gap-4">
                                <div className="flex items-center gap-2 text-xs">
                                    <span className="text-[#5f6368]">Total:</span>
                                    <span className="font-semibold text-[#202124] bg-[#f1f3f4] px-2 py-0.5 rounded-full">{logEntries.length}</span>
                                </div>
                                {(() => {
                                    const errorCount = logEntries.filter(e => e.severity === 'ERROR').length;
                                    const warnCount = logEntries.filter(e => e.severity === 'WARNING').length;
                                    return (
                                        <>
                                            {errorCount > 0 && (
                                                <div className="flex items-center gap-1.5 text-xs">
                                                    <span className="w-2 h-2 rounded-full bg-red-500" />
                                                    <span className="text-red-600 font-semibold">{errorCount} errors</span>
                                                </div>
                                            )}
                                            {warnCount > 0 && (
                                                <div className="flex items-center gap-1.5 text-xs">
                                                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                                                    <span className="text-amber-600 font-semibold">{warnCount} warnings</span>
                                                </div>
                                            )}
                                        </>
                                    );
                                })()}
                            </div>
                        )}

                        {/* Log entries */}
                        <div className="bg-[#1e1e1e] rounded-xl border border-[#333] shadow-sm overflow-hidden">
                            <div className="px-4 py-2.5 border-b border-[#333] flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Terminal size={13} className="text-[#4ec9b0]" />
                                    <span className="text-xs font-medium text-[#ccc]">readpaper-{logService}</span>
                                </div>
                                <span className="text-[10px] text-[#666]">
                                    {logEntries.length > 0 && `${logEntries.length} entries`}
                                </span>
                            </div>
                            <div className="max-h-[600px] overflow-y-auto" style={{ scrollbarWidth: 'thin' }}>
                                {logLoading && logEntries.length === 0 && (
                                    <div className="flex items-center justify-center py-16">
                                        <RefreshCw size={18} className="animate-spin text-blue-400 mr-2" />
                                        <span className="text-xs text-[#666]">Querying Cloud Run logs...</span>
                                    </div>
                                )}
                                {!logLoading && logEntries.length === 0 && (
                                    <div className="py-16 text-center">
                                        <Terminal size={24} className="mx-auto text-[#444] mb-2" />
                                        <p className="text-xs text-[#666]">No log entries. Click &quot;Fetch Logs&quot; to query.</p>
                                    </div>
                                )}
                                {logEntries.map((entry, i) => {
                                    const isExpanded = expandedLogIdx === i;
                                    const isLong = entry.message.length > 200;
                                    const sevColor: Record<string, string> = {
                                        ERROR: 'bg-red-500/20 text-red-400 border-red-500/30',
                                        WARNING: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
                                        INFO: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
                                        DEFAULT: 'bg-[#333] text-[#999] border-[#444]',
                                        DEBUG: 'bg-[#333] text-[#777] border-[#444]',
                                    };
                                    const colors = sevColor[entry.severity] || sevColor.DEFAULT;
                                    return (
                                        <div
                                            key={i}
                                            className={`border-b border-[#2a2a2a] px-4 py-2 hover:bg-[#252525] transition-colors ${entry.severity === 'ERROR' ? 'bg-red-900/10' : ''
                                                }`}
                                        >
                                            <div className="flex items-start gap-2.5">
                                                {/* Severity badge */}
                                                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 mt-0.5 ${colors}`}>
                                                    {entry.severity || 'LOG'}
                                                </span>
                                                {/* Timestamp */}
                                                <span className="text-[10px] text-[#666] font-mono flex-shrink-0 mt-0.5 tabular-nums" style={{ minWidth: 75 }}>
                                                    {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString('en-US', { hour12: false }) : ''}
                                                </span>
                                                {/* Message */}
                                                <div className="flex-1 min-w-0">
                                                    <pre className={`text-[11px] font-mono text-[#d4d4d4] whitespace-pre-wrap break-words leading-relaxed ${!isExpanded && isLong ? 'line-clamp-3' : ''
                                                        }`}>
                                                        {entry.message}
                                                    </pre>
                                                    {isLong && (
                                                        <button
                                                            onClick={() => setExpandedLogIdx(isExpanded ? null : i)}
                                                            className="text-[10px] text-blue-400 hover:text-blue-300 mt-1 flex items-center gap-0.5"
                                                        >
                                                            <Eye size={10} />
                                                            {isExpanded ? 'Collapse' : 'Expand'}
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </>
                )}

                {/* Loading overlay for initial load */}
                {loading && !stats && (
                    <div className="flex items-center justify-center py-24">
                        <RefreshCw size={24} className="animate-spin text-blue-400 mr-3" />
                        <span className="text-sm text-[#9aa0a6]">Loading admin data...</span>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, color, label, value, sub }: {
    icon: any; color: string; label: string; value: string | number; sub?: string;
}) {
    const colors: Record<string, { bg: string; text: string }> = {
        blue: { bg: 'bg-blue-50', text: 'text-[#1a73e8]' },
        green: { bg: 'bg-green-50', text: 'text-green-600' },
        purple: { bg: 'bg-purple-50', text: 'text-purple-600' },
        amber: { bg: 'bg-amber-50', text: 'text-amber-600' },
    };
    const c = colors[color] || colors.blue;
    return (
        <div className="bg-white rounded-xl border border-[#dadce0] p-5 flex items-center gap-4 shadow-sm">
            <div className={`w-10 h-10 ${c.bg} rounded-lg flex items-center justify-center`}>
                <Icon size={20} className={c.text} />
            </div>
            <div>
                <div className="text-2xl font-bold text-[#202124]">{value}</div>
                <div className="text-xs text-[#5f6368]">{label}</div>
                {sub && <div className="text-[10px] text-[#9aa0a6] mt-0.5">{sub}</div>}
            </div>
        </div>
    );
}

function ThSortable<T extends string>({ label, sortKey, current, onSort }: {
    label: string; sortKey: T; current: { key: T; dir: SortDir }; onSort: (key: T) => void;
}) {
    return (
        <th
            className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider cursor-pointer hover:text-[#202124] select-none"
            onClick={() => onSort(sortKey)}
        >
            {label}
            {current.key === sortKey && (
                current.dir === 'asc' ? <ChevronUp size={12} className="inline ml-0.5" /> : <ChevronDown size={12} className="inline ml-0.5" />
            )}
        </th>
    );
}

// ── Chart drawing (Canvas API) ───────────────────────────────────────────────

function drawChart(canvas: HTMLCanvasElement, data: DailyStat[]) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const pad = { top: 30, right: 70, bottom: 50, left: 60 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    // Clear
    ctx.clearRect(0, 0, W, H);

    // Data
    const papersMax = Math.max(...data.map(d => d.papers_count), 1);
    const tokensMax = Math.max(...data.map(d => d.total_in_tokens + d.total_out_tokens), 1);

    // Grid lines
    ctx.strokeStyle = '#f1f3f4';
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
        const y = pad.top + (chartH / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(W - pad.right, y);
        ctx.stroke();
    }

    // Y-axis labels (left: papers)
    ctx.fillStyle = '#1a73e8';
    ctx.font = '10px system-ui, sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= gridLines; i++) {
        const y = pad.top + (chartH / gridLines) * i;
        const val = Math.round(papersMax * (1 - i / gridLines));
        ctx.fillText(val.toString(), pad.left - 8, y + 3);
    }

    // Y-axis labels (right: tokens)
    ctx.fillStyle = '#e8710a';
    ctx.textAlign = 'left';
    for (let i = 0; i <= gridLines; i++) {
        const y = pad.top + (chartH / gridLines) * i;
        const val = tokensMax * (1 - i / gridLines);
        ctx.fillText(fmtTokens(Math.round(val)), W - pad.right + 8, y + 3);
    }

    // X-axis labels
    ctx.fillStyle = '#9aa0a6';
    ctx.textAlign = 'center';
    ctx.font = '9px system-ui, sans-serif';
    const labelInterval = Math.max(1, Math.floor(data.length / 10));
    data.forEach((d, i) => {
        if (i % labelInterval === 0 || i === data.length - 1) {
            const x = pad.left + (chartW / Math.max(data.length - 1, 1)) * i;
            // Show MM-DD
            const dateLabel = d.date.slice(5); // "02-23"
            ctx.save();
            ctx.translate(x, H - pad.bottom + 14);
            ctx.rotate(-Math.PI / 6);
            ctx.fillText(dateLabel, 0, 0);
            ctx.restore();
        }
    });

    // Draw bars for papers
    const barWidth = Math.max(4, Math.min(20, chartW / data.length * 0.5));
    ctx.fillStyle = 'rgba(26, 115, 232, 0.3)';
    data.forEach((d, i) => {
        const x = pad.left + (chartW / Math.max(data.length - 1, 1)) * i - barWidth / 2;
        const h = (d.papers_count / papersMax) * chartH;
        const y = pad.top + chartH - h;
        ctx.beginPath();
        // Rounded top rect
        const r = Math.min(3, barWidth / 2);
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + barWidth, y, x + barWidth, y + h, r);
        ctx.arcTo(x + barWidth, y + h, x, y + h, 0);
        ctx.arcTo(x, y + h, x, y, 0);
        ctx.arcTo(x, y, x + barWidth, y, r);
        ctx.fill();

        // Solid border
        ctx.strokeStyle = 'rgba(26, 115, 232, 0.6)';
        ctx.lineWidth = 1;
        ctx.stroke();
    });

    // Draw token line
    ctx.strokeStyle = '#e8710a';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    data.forEach((d, i) => {
        const x = pad.left + (chartW / Math.max(data.length - 1, 1)) * i;
        const tokensTotal = d.total_in_tokens + d.total_out_tokens;
        const y = pad.top + chartH - (tokensTotal / tokensMax) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Token dots
    ctx.fillStyle = '#e8710a';
    data.forEach((d, i) => {
        const x = pad.left + (chartW / Math.max(data.length - 1, 1)) * i;
        const tokensTotal = d.total_in_tokens + d.total_out_tokens;
        const y = pad.top + chartH - (tokensTotal / tokensMax) * chartH;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
    });

    // Axis labels
    ctx.save();
    ctx.fillStyle = '#1a73e8';
    ctx.font = 'bold 10px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.translate(14, pad.top + chartH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Papers', 0, 0);
    ctx.restore();

    ctx.save();
    ctx.fillStyle = '#e8710a';
    ctx.font = 'bold 10px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.translate(W - 10, pad.top + chartH / 2);
    ctx.rotate(Math.PI / 2);
    ctx.fillText('Tokens', 0, 0);
    ctx.restore();
}
