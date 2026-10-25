import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Waypoints, Scale } from 'lucide-react';

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const linkTo = (pathname: string) => ({ pathname, search: location.search });

  return (
    <aside className="fh-sidebar">
      <div className="fh-brand">
        <div className="fh-brand-logo-wrap">
          <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path d="M16 2L5 9.5L16 15.5L27 9.5L16 2Z" fill="#FFFFFF" fillOpacity="0.95" />
            <path d="M5 9.5L16 15.5V29.5L5 22V9.5Z" fill="#FFFFFF" fillOpacity="0.75" />
            <path d="M27 9.5L16 15.5V29.5L27 22V9.5Z" fill="#FFFFFF" fillOpacity="0.55" />
            <path d="M16 15.5L21 19.5L16 23.5L11 19.5L16 15.5Z" fill="#10B981" />
          </svg>
        </div>
        <div className="fh-brand-text">
          <div className="fh-brand-title">FairHold</div>
          <div className="fh-brand-subtitle">Fund-flow investigation</div>
        </div>
      </div>

      <nav className="fh-nav-scroll" aria-label="Main navigation">
        <div className="fh-nav-section">
          <div className="fh-nav-heading">WORKSPACE</div>
          <NavLink to={linkTo('/')} end className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <LayoutDashboard size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Case Overview</span>
          </NavLink>
          <NavLink to={linkTo('/money-flow')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Waypoints size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Money Flow</span>
          </NavLink>
          <NavLink to={linkTo('/consensus-lien')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Scale size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Consensus Lien</span>
          </NavLink>
        </div>
      </nav>

      <div className="fh-sidebar-bottom">
        <div className="fh-env-card">
          <div className="fh-env-title">Local demonstration</div>
          <div className="fh-env-sub">Synthetic ledger · no live bank feed</div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
