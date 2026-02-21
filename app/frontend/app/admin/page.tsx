'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    Users, FileText, TrendingUp, RefreshCw,
    ChevronUp, ChevronDown, Search, ArrowLeft,
    Shield, BookOpen, Calendar
} from 'lucide-react';

const API_BASE = '/backend';
const ADMIN_EMAIL = 'chinachenzeyu@gmail.com';

interface AdminPaper {
    user_id: string;
    id: string;
    title?: string;
    authors?: string[];
    categories?: string[];
    abstract?: string;
    versions?: Array<{ model: string; status: string; timestamp: string }>;
}

interface AdminStats {
    total_users: number;
    total_papers: number;
    user_ids: string[];
}

type SortKey = 'user_id' | 'id' | 'title';
type SortDir = 'asc' | 'desc';

export default function AdminPage() {
    const router = useRouter();

    const [papers, setPapers] = useState<AdminPaper[]>([]);
    const [stats, setStats] = useState<AdminStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [search, setSearch] = useState('');
    const [sortKey, setSortKey] = useState<SortKey>('user_id');
    const [sortDir, setSortDir] = useState<SortDir>('asc');
    const [selectedUser, setSelectedUser] = useState<string>('all');

    const getAuthHeaders = (): HeadersInit => {
        return { 'Content-Type': 'application/json' };
    };

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        setError('');
        try {
            const headers = getAuthHeaders();
            const [papersRes, statsRes] = await Promise.all([
                fetch(`${API_BASE}/admin/papers`, { headers }),
                fetch(`${API_BASE}/admin/stats`, { headers }),
            ]);
            if (!papersRes.ok) throw new Error(`Papers fetch failed: ${papersRes.status}`);
            if (!statsRes.ok) throw new Error(`Stats fetch failed: ${statsRes.status}`);
            setPapers(await papersRes.json());
            setStats(await statsRes.json());
        } catch (e: any) {
            setError(e.message || 'Failed to load admin data');
        } finally {
            setLoading(false);
        }
    };

    // ── Derived data ──
    const userList = stats?.user_ids ?? [];
    const filtered = papers
        .filter(p => selectedUser === 'all' || p.user_id === selectedUser)
        .filter(p => {
            const q = search.toLowerCase();
            return !q || p.id.includes(q) || (p.title ?? '').toLowerCase().includes(q) || p.user_id.toLowerCase().includes(q);
        })
        .sort((a, b) => {
            const av = (a[sortKey] ?? '').toString().toLowerCase();
            const bv = (b[sortKey] ?? '').toString().toLowerCase();
            return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        });

    const toggleSort = (key: SortKey) => {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('asc'); }
    };

    const SortIcon = ({ k }: { k: SortKey }) => sortKey === k
        ? (sortDir === 'asc' ? <ChevronUp size={12} className="inline ml-0.5" /> : <ChevronDown size={12} className="inline ml-0.5" />)
        : null;

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
                <span className="text-xs text-[#9aa0a6] bg-blue-50 px-2 py-0.5 rounded-full font-mono">
                    Admin (auth disabled)
                </span>
            </div>

            <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
                {/* Stats Cards */}
                {stats && (
                    <div className="grid grid-cols-3 gap-4">
                        <div className="bg-white rounded-xl border border-[#dadce0] p-5 flex items-center gap-4 shadow-sm">
                            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                                <Users size={20} className="text-[#1a73e8]" />
                            </div>
                            <div>
                                <div className="text-2xl font-bold text-[#202124]">{stats.total_users}</div>
                                <div className="text-xs text-[#5f6368]">Total Users</div>
                            </div>
                        </div>
                        <div className="bg-white rounded-xl border border-[#dadce0] p-5 flex items-center gap-4 shadow-sm">
                            <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center">
                                <BookOpen size={20} className="text-green-600" />
                            </div>
                            <div>
                                <div className="text-2xl font-bold text-[#202124]">{stats.total_papers}</div>
                                <div className="text-xs text-[#5f6368]">Papers Translated</div>
                            </div>
                        </div>
                        <div className="bg-white rounded-xl border border-[#dadce0] p-5 flex items-center gap-4 shadow-sm">
                            <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center">
                                <TrendingUp size={20} className="text-purple-600" />
                            </div>
                            <div>
                                <div className="text-2xl font-bold text-[#202124]">
                                    {stats.total_users > 0 ? (stats.total_papers / stats.total_users).toFixed(1) : '—'}
                                </div>
                                <div className="text-xs text-[#5f6368]">Papers / User (avg)</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Filters */}
                <div className="flex gap-3 items-center">
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
                    <span className="text-xs text-[#9aa0a6]">{filtered.length} paper{filtered.length !== 1 ? 's' : ''}</span>
                </div>

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
                        ⚠ {error}
                    </div>
                )}

                {/* Papers Table */}
                <div className="bg-white rounded-xl border border-[#dadce0] overflow-hidden shadow-sm">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-[#dadce0] bg-[#f8f9fa]">
                                <th
                                    className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider cursor-pointer hover:text-[#202124] select-none"
                                    onClick={() => toggleSort('user_id')}
                                >
                                    User <SortIcon k="user_id" />
                                </th>
                                <th
                                    className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider cursor-pointer hover:text-[#202124] select-none"
                                    onClick={() => toggleSort('id')}
                                >
                                    Paper ID <SortIcon k="id" />
                                </th>
                                <th
                                    className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider cursor-pointer hover:text-[#202124] select-none"
                                    onClick={() => toggleSort('title')}
                                >
                                    Title <SortIcon k="title" />
                                </th>
                                <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">
                                    Authors
                                </th>
                                <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">
                                    Categories
                                </th>
                                <th className="px-4 py-3 text-left text-[11px] font-semibold text-[#5f6368] uppercase tracking-wider">
                                    Versions
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && (
                                <tr>
                                    <td colSpan={6} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">
                                        <RefreshCw size={18} className="animate-spin inline mr-2 text-blue-400" />
                                        Loading all users&apos; data...
                                    </td>
                                </tr>
                            )}
                            {!loading && filtered.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-4 py-12 text-center text-[#9aa0a6] text-xs">
                                        No papers found
                                    </td>
                                </tr>
                            )}
                            {!loading && filtered.map((p, i) => (
                                <tr
                                    key={`${p.user_id}-${p.id}`}
                                    className={`border-b border-[#f1f3f4] hover:bg-[#f8f9fa] transition-colors ${i % 2 === 0 ? '' : 'bg-[#fafafa]'}`}
                                >
                                    <td className="px-4 py-3">
                                        <span className="text-[11px] font-mono text-[#5f6368] bg-[#f1f3f4] px-2 py-0.5 rounded-full truncate max-w-[160px] block">
                                            {p.user_id}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <a
                                            href={`https://arxiv.org/abs/${p.id}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-[#1a73e8] hover:underline font-mono text-xs"
                                        >
                                            {p.id}
                                        </a>
                                    </td>
                                    <td className="px-4 py-3 max-w-xs">
                                        <div className="text-xs text-[#202124] leading-snug line-clamp-2">
                                            {p.title || <span className="text-[#9aa0a6] italic">No title</span>}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 max-w-[140px]">
                                        <div className="text-[11px] text-[#5f6368] line-clamp-1">
                                            {p.authors?.slice(0, 3).join(', ')}
                                            {(p.authors?.length ?? 0) > 3 && ` +${(p.authors?.length ?? 0) - 3}`}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex flex-wrap gap-1">
                                            {p.categories?.slice(0, 2).map(c => (
                                                <span key={c} className="text-[9px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">{c}</span>
                                            ))}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex flex-wrap gap-1">
                                            {p.versions?.map(v => (
                                                <span
                                                    key={v.model}
                                                    className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${v.status === 'completed'
                                                        ? 'bg-green-50 text-green-700'
                                                        : 'bg-yellow-50 text-yellow-700'
                                                        }`}
                                                >
                                                    {v.model} · {v.status}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
