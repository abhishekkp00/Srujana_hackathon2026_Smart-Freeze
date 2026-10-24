import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, LogOut, ShieldCheck } from 'lucide-react';

interface CurrentUser {
  user_id: string;
  display_name: string;
  role: string;
  institution_id: string;
  assigned_case_count: number;
}

interface DemoPersona {
  persona_id: string;
  display_name: string;
  role: string;
  assigned_case_count: number;
  institution_id: string;
}

interface NavbarProps {
  title: string;
  subtitle?: string;
  section?: string;
  currentUser: CurrentUser;
  personas: DemoPersona[];
  onSelectPersona: (personaId: string) => Promise<void>;
  onSignOut: () => void;
}

const initialsFrom = (name: string): string =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase();

export const Navbar: React.FC<NavbarProps> = ({
  title,
  subtitle,
  section = 'Workspace',
  currentUser,
  personas,
  onSelectPersona,
  onSignOut,
}) => {
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const closeOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  const choosePersona = async (personaId: string) => {
    setSwitching(true);
    try {
      await onSelectPersona(personaId);
      setOpen(false);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <header className="fh-topbar">
      <div className="fh-topbar-main">
        <div className="fh-breadcrumb">
          <span>FairHold</span><span className="fh-breadcrumb-divider">/</span><span>{section}</span>
        </div>
        <h1 className="fh-topbar-title">{title}</h1>
        {subtitle && <p className="fh-topbar-subtitle">{subtitle}</p>}
      </div>

      <div className="fh-topbar-actions">
        <div className="fh-env-chip"><span className="status-dot status-dot--warning" /><span>Local demo · synthetic data</span></div>
        <div className="fh-user-menu" ref={menuRef}>
          <button
            className="fh-profile-trigger"
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            <span className="fh-profile-avatar">{initialsFrom(currentUser.display_name)}</span>
            <span className="fh-profile-details">
              <span className="fh-profile-name">{currentUser.display_name}</span>
              <span className="fh-profile-role">{currentUser.role.replace(/_/g, ' ')}</span>
            </span>
            <ChevronDown size={14} />
          </button>

          {open && (
            <div className="fh-user-dropdown" role="menu">
              <div className="fh-user-dropdown-heading">
                <ShieldCheck size={14} />
                <span>Local demonstration identities</span>
              </div>
              <p className="fh-user-dropdown-note">Role switching is simulated and is not production authentication.</p>
              {personas.map((persona) => (
                <button
                  type="button"
                  role="menuitem"
                  key={persona.persona_id}
                  disabled={switching || persona.persona_id === currentUser.user_id}
                  onClick={() => void choosePersona(persona.persona_id)}
                  className={"fh-user-option" + (persona.persona_id === currentUser.user_id ? " is-current" : "")}
                >
                  <span className="fh-profile-avatar fh-profile-avatar--small">{initialsFrom(persona.display_name)}</span>
                  <span className="fh-user-option-copy">
                    <span className="fh-profile-name">{persona.display_name}</span>
                    <span className="fh-profile-role">{persona.role} · {persona.assigned_case_count} assigned cases</span>
                  </span>
                  {persona.persona_id === currentUser.user_id && <span className="fh-current-label">Current</span>}
                </button>
              ))}
              <div className="fh-user-dropdown-footer">
                <span className="fh-profile-role">{currentUser.institution_id}</span>
                <button type="button" className="fh-signout-button" onClick={() => { setOpen(false); onSignOut(); }}>
                  <LogOut size={13} /> End session
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
