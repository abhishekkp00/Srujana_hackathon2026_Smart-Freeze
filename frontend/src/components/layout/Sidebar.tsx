import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Waypoints,
  Scale,
  ShieldCheck,
  TableProperties,
  Crosshair,
  Cpu,
  ClipboardCheck,
  ShieldAlert,
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const linkTo = (pathname: string) => ({ pathname, search: location.search });

  return (
    <aside className="fh-sidebar">
      <div className="fh-brand">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-[#625ee8] text-white flex items-center justify-center font-bold text-xs">
            SF
          </div>
          <div>
            <div className="fh-brand-title">Smart-Freeze</div>
            <div className="fh-brand-subtitle">Financial investigation</div>
          </div>
        </div>
      </div>

      <nav className="fh-nav-scroll" aria-label="Main navigation">
        <div className="fh-nav-section">
          <div className="fh-nav-heading">WORKSPACE</div>
          <NavLink to={linkTo('/')} end className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <LayoutDashboard size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Overview</span>
          </NavLink>
        </div>

        <div className="fh-nav-section mt-3">
          <div className="fh-nav-heading">INVESTIGATION</div>
          <NavLink to={linkTo('/money-flow')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Waypoints size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Money flow</span>
          </NavLink>
          <NavLink to={linkTo('/consensus-lien')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Scale size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Consensus Lien</span>
          </NavLink>
          <NavLink to={linkTo('/recommendations')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <ShieldCheck size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Recommended actions</span>
          </NavLink>
          <NavLink to={linkTo('/transactions')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <TableProperties size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Transaction ledger</span>
          </NavLink>
        </div>

        <div className="fh-nav-section mt-3">
          <div className="fh-nav-heading">TESTING &amp; ML</div>
          <NavLink to={linkTo('/attack-lab')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Crosshair size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Attack Lab</span>
          </NavLink>
          <NavLink to={linkTo('/ml-analysis')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Cpu size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>ML mule scoring</span>
          </NavLink>
          <NavLink to={linkTo('/data-quality')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <ClipboardCheck size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Data quality</span>
          </NavLink>
        </div>

        <div className="fh-nav-section mt-3">
          <div className="fh-nav-heading">GOVERNANCE</div>
          <NavLink to={linkTo('/security-audit')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <ShieldAlert size={15} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Security &amp; audit</span>
          </NavLink>
        </div>
      </nav>

      <div className="fh-sidebar-bottom">
        <div className="fh-env-card">
          <div className="fh-env-title">Local demonstration</div>
          <div className="fh-env-sub">Synthetic records · no live bank connection</div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
