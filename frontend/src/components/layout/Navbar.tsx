import React from 'react';
import { useLocation } from 'react-router-dom';
import { Search, Command, ChevronDown, Bell, CircleHelp } from 'lucide-react';

interface NavbarProps {
  title: string;
  subtitle?: string;
  section?: string;
  selectedCaseId?: string;
  onSelectCaseId?: (caseId: string) => void;
  availableCases?: string[];
}

export const Navbar: React.FC<NavbarProps> = ({ title, subtitle, section = 'Workspace', selectedCaseId, onSelectCaseId, availableCases = [] }) => {
  const location = useLocation();
  return (
    <header className="fh-topbar">
      <div className="fh-topbar-main">
        <div className="fh-breadcrumb"><span>FairHold</span><span className="fh-breadcrumb-divider">/</span><span>{section}</span></div>
        <h1 className="fh-topbar-title">{title}</h1>
        {subtitle && <p className="fh-topbar-subtitle">{subtitle}</p>}
      </div>
      <div className="fh-topbar-actions">
        {onSelectCaseId && (
          <label className="fh-case-select"><span>Case</span><select value={selectedCaseId} onChange={(e) => onSelectCaseId(e.target.value)}>{availableCases.map((id) => <option value={id} key={id}>{id}</option>)}</select><ChevronDown size={13} /></label>
        )}
        <div className="fh-env-chip"><span className="status-dot status-dot--warning" /><span>Demo data</span></div>
        <button className="fh-icon-button" type="button" aria-label="Search" onClick={() => window.dispatchEvent(new CustomEvent('fairhold:focus-search'))}><Search size={17} /></button>
        <button className="fh-icon-button" type="button" aria-label="Help" onClick={() => window.dispatchEvent(new CustomEvent('fairhold:show-help', { detail: { path: location.pathname } }))}><CircleHelp size={17} /></button>
      </div>
    </header>
  );
};
