import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  GitFork,
  Scale,
  ShieldAlert,
  Database,
  ShieldCheck,
  AlertTriangle,
  Cpu,
  Fingerprint,
} from 'lucide-react';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/explorer', label: 'Transaction Explorer', icon: GitFork },
  { to: '/consensus-lien', label: 'Consensus Lien', icon: Scale },
  { to: '/traceproof', label: 'TraceProof Multi-Rail', icon: Fingerprint },
  { to: '/investigation', label: 'Investigation Review', icon: ShieldAlert },
  { to: '/ml-analysis', label: 'ML Fraud Classifier', icon: Cpu },
  { to: '/data-quality', label: 'Data Quality & Audit', icon: Database },
  { to: '/security', label: 'Security & Audit', icon: ShieldCheck },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-slate-900 text-slate-200 flex flex-col flex-shrink-0 border-r border-slate-800 select-none">
      {/* Brand & Logo */}
      <div className="p-5 border-b border-slate-800 flex items-center space-x-3">
        <div className="w-10 h-10 rounded-lg bg-teal-600 flex items-center justify-center text-white shadow-md shadow-teal-900/30">
          <ShieldCheck className="w-6 h-6" />
        </div>
        <div>
          <div className="font-bold text-lg tracking-wide text-white flex items-center">
            Smart-Freeze
            <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-semibold bg-teal-500/20 text-teal-400 rounded border border-teal-500/30">
              MVP
            </span>
          </div>
          <p className="text-xs text-slate-400 font-medium">Fraud Investigation Support</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1.5 overflow-y-auto">
        <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
          Investigation Modules
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-teal-600/20 text-teal-300 border border-teal-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                }`
              }
            >
              <Icon className="w-4 h-4 mr-3 flex-shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Governance & Human-in-the-Loop Footer Notice */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/60 text-xs">
        <div className="flex items-center text-amber-400 font-semibold mb-1">
          <AlertTriangle className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />
          <span>Human-in-the-Loop</span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          Estimates are investigative heuristics. Automated freezes or case closures are strictly prohibited.
        </p>
      </div>
    </aside>
  );
};
