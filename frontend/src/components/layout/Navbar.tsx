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

export const Navbar: React.FC<NavbarProps> = ({ title, subtitle, section = 'Workspace', currentUser, onSignOut }) => (
  <header className="fh-header">
    <div className="min-w-0">
      <div className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
        Smart-Freeze <span className="mx-1 text-slate-300">/</span> {section}
      </div>
      <h1 className="mt-1 text-base font-semibold tracking-tight text-slate-900">{title}</h1>
      {subtitle && <p className="mt-1 max-w-2xl text-[12px] leading-4 text-slate-500">{subtitle}</p>}
    </div>

    <div className="fh-header-actions">
      <span className="hidden sm:inline text-[11px] text-slate-500">Synthetic demo data</span>
      <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
        <UserRound size={15} className="text-slate-500" />
        <div className="hidden sm:block">
          <div className="text-xs font-medium text-slate-800">{currentUser.display_name}</div>
          <div className="text-[10px] text-slate-500">{currentUser.assigned_case_count} cases in ledger</div>
        </div>
        <button type="button" onClick={onSignOut} className="ml-1 inline-flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-900" title="End local demo session">
          <LogOut size={13} /><span className="hidden md:inline">Exit</span>
        </button>
      </div>
    </div>
  </header>
);
export default Navbar;
