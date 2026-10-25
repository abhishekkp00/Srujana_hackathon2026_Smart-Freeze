import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Waypoints, Scale, ShieldCheck, Crosshair } from 'lucide-react';

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const linkTo = (pathname: string) => ({ pathname, search: location.search });

  return (
    <aside className="fh-sidebar">
      <div className="fh-brand">
        <div className="fh-brand-title">Smart-Freeze</div>
        <div className="fh-brand-subtitle">Financial investigation</div>
      </div>

      <nav className="fh-nav-scroll" aria-label="Main navigation">
        <div className="fh-nav-section">
          <div className="fh-nav-heading">WORKSPACE</div>
          <NavLink to={linkTo('/')} end className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <LayoutDashboard size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Case overview</span>
          </NavLink>
          <NavLink to={linkTo('/money-flow')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Waypoints size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Money flow</span>
          </NavLink>
          <NavLink to={linkTo('/consensus-lien')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Scale size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Consensus Lien</span>
          </NavLink>
          <NavLink to={linkTo('/recommendations')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <ShieldCheck size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Recommended actions</span>
          </NavLink>
          <NavLink to={linkTo('/attack-lab')} className={({ isActive }) => `fh-sub-link ${isActive ? 'is-active' : ''}`}>
            <Crosshair size={16} strokeWidth={1.8} className="fh-sub-icon" />
            <span>Attack Lab</span>
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
