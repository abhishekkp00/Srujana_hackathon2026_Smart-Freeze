import React, { useState } from 'react';
import { LogOut, Search, Shield, ArrowUpRight } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

interface CurrentUser {
  user_id: string;
  display_name: string;
  role: string;
  institution_id: string;
  assigned_case_count: number;
}

interface NavbarProps {
  title: string;
  subtitle?: string;
  section?: string;
  currentUser: CurrentUser;
  onSignOut: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  title,
  subtitle,
  section = 'Workspace',
  currentUser,
  onSignOut,
}) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeCase = searchParams.get('case') || 'CASE-2026-001';
  const [searchInput, setSearchInput] = useState('');

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchInput.trim()) return;
    const query = searchInput.trim().toUpperCase();
    if (query.startsWith('CASE-') || query.includes('2026')) {
      navigate(`/money-flow?case=${encodeURIComponent(query)}`);
    } else {
      navigate(`/?q=${encodeURIComponent(searchInput.trim())}`);
    }
  };

  const getInitials = (name: string) => {
    return name
      .split(' ')
      .map((part) => part[0])
      .filter(Boolean)
      .slice(0, 2)
      .join('')
      .toUpperCase() || 'SF';
  };

  return (
    <header className="fh-header">
      {/* Left: Title & Section Breadcrumb */}
      <div className="min-w-0 flex-shrink-0">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Smart-Freeze <span className="mx-1 text-slate-300">/</span> {section}
        </div>
        <h1 className="mt-0.5 text-sm font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && (
          <p className="hidden lg:block text-[11px] leading-tight text-slate-500 truncate max-w-md">
            {subtitle}
          </p>
        )}
      </div>

      {/* Center: Global Search Bar */}
      <form onSubmit={handleSearchSubmit} className="hidden md:flex items-center flex-1 max-w-md mx-4">
        <div className="relative w-full">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search size={13} />
          </div>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search cases, accounts, transaction reference..."
            className="w-full pl-8 pr-12 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-md focus:bg-white focus:border-[#625ee8] focus:outline-none transition-colors placeholder:text-slate-400"
          />
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
            <span className="text-[10px] font-medium text-slate-400 bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5">
              ⌘K
            </span>
          </div>
        </div>
      </form>

      {/* Right: Active Investigation Context & Identity */}
      <div className="fh-header-actions flex items-center gap-3">
        {/* Active Investigation Context Pill */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-indigo-50 border border-indigo-100 rounded text-[11px] text-indigo-700">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 animate-pulse" />
          <span className="font-medium">Active:</span>
          <button
            type="button"
            onClick={() => navigate(`/money-flow?case=${encodeURIComponent(activeCase)}`)}
            className="font-mono font-semibold hover:underline inline-flex items-center gap-0.5"
            title="Open active case in Money Flow"
          >
            {activeCase}
            <ArrowUpRight size={11} />
          </button>
        </div>

        {/* User Identity Pill */}
        <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
          <div className="w-7 h-7 rounded-full bg-slate-800 text-white flex items-center justify-center font-semibold text-[11px] tracking-tight">
            {getInitials(currentUser.display_name)}
          </div>
          <div className="hidden sm:block text-left">
            <div className="text-xs font-semibold text-slate-800 leading-tight">
              {currentUser.display_name}
            </div>
            <div className="text-[10px] text-slate-500 leading-tight">
              {currentUser.role.replace(/_/g, ' ')}
            </div>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="ml-1 p-1.5 text-slate-400 hover:text-slate-800 rounded hover:bg-slate-100 transition-colors"
            title="End demo session"
            aria-label="Sign out"
          >
            <LogOut size={13} />
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
