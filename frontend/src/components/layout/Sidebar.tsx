import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, ArrowLeftRight, Scale, ShieldAlert, Database, ShieldCheck, Fingerprint, Cpu, ChevronRight } from 'lucide-react';

const navGroups = [
  { label: 'Workspace', items: [{ to: '/', label: 'Case overview', icon: Activity }] },
  { label: 'Investigation', items: [
    { to: '/explorer', label: 'Transaction explorer', icon: ArrowLeftRight },
    { to: '/traceproof', label: 'TraceProof', icon: Fingerprint },
    { to: '/investigation', label: 'Case review', icon: ShieldAlert },
  ]},
  { label: 'Analysis', items: [
    { to: '/consensus-lien', label: 'Fund tracing', icon: Scale },
    { to: '/ml-analysis', label: 'Model evaluation', icon: Cpu },
  ]},
  { label: 'Governance', items: [
    { to: '/data-quality', label: 'Data quality', icon: Database },
    { to: '/security', label: 'Security review', icon: ShieldCheck },
  ]},
];

export const Sidebar: React.FC = () => (
  <aside className="fh-sidebar">
    <div className="fh-brand">
      <div className="fh-brand-mark"><span>fh</span><i /></div>
      <div className="fh-brand-copy">
        <div className="fh-brand-name">FairHold</div>
        <div className="fh-brand-caption">Financial evidence workspace</div>
      </div>
    </div>

    <div className="fh-side-context">
      <span className="eyebrow">Workspace</span>
      <div className="fh-workspace-select"><span className="fh-workspace-avatar">FI</span><span className="fh-workspace-label">Financial investigations</span><ChevronRight size={14} /></div>
    </div>

    <nav className="fh-navigation" aria-label="Primary navigation">
      {navGroups.map((group) => (
        <div className="fh-nav-group" key={group.label}>
          <div className="fh-nav-label">{group.label}</div>
          {group.items.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `fh-nav-link ${isActive ? 'is-active' : ''}`}>
                <Icon size={16} strokeWidth={1.8} />
                <span>{item.label}</span>
                {item.to === '/traceproof' && <span className="fh-nav-mark" aria-label="Signature workflow" />}
              </NavLink>
            );
          })}
        </div>
      ))}
    </nav>

    <div className="fh-sidebar-bottom">
      <div className="fh-environment">
        <span className="status-dot status-dot--warning" />
        <div><div className="fh-environment-title">Demonstration environment</div><div className="fh-environment-note">Synthetic financial records</div></div>
      </div>
      <div className="fh-sidebar-footer">
        <span>FAIRHOLD / FINANCIAL INVESTIGATIONS</span>
        <span>BUILD 0.1</span>
      </div>
    </div>
  </aside>
);
