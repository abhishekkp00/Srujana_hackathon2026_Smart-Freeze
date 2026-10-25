import React from 'react';
import { LogOut, UserRound } from 'lucide-react';

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
  return (
    <header className="fh-header" style={{ minHeight: 70, height: 'auto', paddingTop: 12, paddingBottom: 12 }}>
      <div className="min-w-0">
        <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
          FairHold <span className="mx-1 text-slate-300">/</span> {section}
        </div>
        <h1 className="mt-1 text-base font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-[11px] leading-4 text-slate-500">{subtitle}</p>}
      </div>

      <div className="fh-header-actions">
        <div className="hidden sm:flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[10px] font-medium text-amber-800">
          <span className="status-dot status-dot--warning" />
          SYNTHETIC DEMO DATA
        </div>
        <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5">
          <UserRound size={14} className="text-slate-500" />
          <div className="hidden sm:block">
            <div className="text-xs font-semibold text-slate-800">{currentUser.display_name}</div>
            <div className="text-[10px] text-slate-500">{currentUser.assigned_case_count} cases in demo ledger</div>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="ml-1 inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-500 hover:text-rose-700"
            title="End local demo session"
          >
            <LogOut size={13} /><span className="hidden md:inline">Exit</span>
          </button>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
