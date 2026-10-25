import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  SlidersHorizontal,
  Fingerprint,
  GitFork,
  Scale,
  ShieldCheck,
  BrainCircuit,
  BarChart3,
  ShieldAlert,
  Activity,
  ChevronRight,
  Radio,
  Waypoints,
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  return (
    <aside className="fh-sidebar">
      {/* Brand Header */}
      <div className="fh-brand">
        <div className="fh-brand-logo-wrap">
          <svg width="30" height="30" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 2L5 9.5L16 15.5L27 9.5L16 2Z" fill="#FFFFFF" fillOpacity="0.95" />
            <path d="M5 9.5L16 15.5V29.5L5 22V9.5Z" fill="#FFFFFF" fillOpacity="0.75" />
            <path d="M27 9.5L16 15.5V29.5L27 22V9.5Z" fill="#FFFFFF" fillOpacity="0.55" />
            <path d="M16 15.5L21 19.5L16 23.5L11 19.5L16 15.5Z" fill="#10B981" />
          </svg>
        </div>
        <div className="fh-brand-text">
          <div className="fh-brand-title">FairHold</div>
          <div className="fh-brand-subtitle">Financial Investigation Platform</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="fh-nav-scroll" aria-label="Main Navigation">
        {/* Top Active Overview Link */}
        <div className="fh-nav-top">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `fh-pill-link ${isActive ? 'is-active' : ''}`}
          >
            <LayoutDashboard size={18} strokeWidth={2} className="fh-nav-icon" />
            <span className="font-medium text-sm">Overview</span>
          </NavLink>
        </div>

        {/* Section: INVESTIGATION */}
        <div className="fh-nav-section">
          <div className="fh-nav-heading">INVESTIGATION</div>
          <NavLink
            to="/investigation"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <FolderKanban size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Case Queue</span>
          </NavLink>

          <NavLink
            to="/explorer"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <SlidersHorizontal size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Transaction Explorer</span>
          </NavLink>
          <NavLink
            to="/money-flow"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <Waypoints size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Money Flow</span>
          </NavLink>


          <NavLink
            to="/traceproof"
            className={({ isActive }) => `fh-sub-link fh-sub-link--composite ${isActive ? 'is-active' : ''}`}
          >
            <Fingerprint size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <div className="flex-1 min-w-0">
              <div className="leading-tight">TraceProof</div>
              <div className="fh-sub-caption">Multi-Rail Investigation</div>
            </div>
            <ChevronRight size={14} className="text-slate-500 opacity-70 group-hover:opacity-100" />
          </NavLink>

          

          <NavLink
            to="/consensus-lien"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <Scale size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Consensus Lien</span>
          </NavLink>

          
        </div>

        {/* Section: ANALYTICS */}
        <div className="fh-nav-section">
          <div className="fh-nav-heading">ANALYTICS</div>
          <NavLink
            to="/ml-analysis"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <BrainCircuit size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>ML Fraud Classifier</span>
          </NavLink>

          <NavLink
            to="/data-quality"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <BarChart3 size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Data Quality</span>
          </NavLink>
        </div>

        {/* Section: GOVERNANCE */}
        <div className="fh-nav-section">
          <div className="fh-nav-heading">GOVERNANCE</div>
          <NavLink
            to="/security"
            className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}
          >
            <ShieldAlert size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Security & Audit</span>
          </NavLink>

          
        </div>
      </nav>

      {/* Sidebar Footer */}
      <div className="fh-sidebar-bottom">
        <div className="fh-env-card">
          <div className="fh-env-icon">
            <Radio size={14} className="text-emerald-400" />
          </div>
          <div className="min-w-0">
            <div className="fh-env-title">Demo Environment</div>
            <div className="fh-env-sub">Synthetic data for evaluation only</div>
          </div>
        </div>

        <div className="fh-version-row">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          <span className="text-xs">Local demonstration build</span>
        </div>
      </div>
    </aside>
  );
};
