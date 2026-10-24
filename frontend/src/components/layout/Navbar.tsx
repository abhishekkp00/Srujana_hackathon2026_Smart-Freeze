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
    <header className="fh-header" style={{ minHeight: 74, height: 'auto', paddingTop: 12, paddingBottom: 12 }}>
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
          LOCAL DEMO · SYNTHETIC DATA
        </div>
        <div className="relative" ref={menuRef}>
          <button
            className="fh-profile-pill"
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            <span className="fh-profile-avatar">{initialsFrom(currentUser.display_name)}</span>
            <span className="fh-profile-info">
              <span className="fh-profile-name">{currentUser.display_name}</span>
              <span className="fh-profile-role">{currentUser.role.replace(/_/g, ' ')}</span>
            </span>
            <ChevronDown size={14} />
          </button>

          {open && (
            <div className="fh-persona-dropdown" role="menu">
              <div className="fh-persona-header">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                  <ShieldCheck size={14} />
                  Demo identities
                </div>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">
                  Simulated roles for testing case permissions. This is not institutional authentication.
                </p>
              </div>
              {personas.map((persona) => (
                <button
                  type="button"
                  role="menuitem"
                  key={persona.persona_id}
                  disabled={switching || persona.persona_id === currentUser.user_id}
                  onClick={() => void choosePersona(persona.persona_id)}
                  className={"fh-persona-item" + (persona.persona_id === currentUser.user_id ? " is-selected" : "")}
                >
                  <span className="fh-persona-item-avatar">{initialsFrom(persona.display_name)}</span>
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block text-xs font-semibold text-slate-800">{persona.display_name}</span>
                    <span className="block text-[10px] text-slate-500">{persona.role} · {persona.assigned_case_count} assigned cases</span>
                  </span>
                  {persona.persona_id === currentUser.user_id && <span className="fh-persona-badge">Current</span>}
                </button>
              ))}
              <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2">
                <span className="max-w-[155px] truncate text-[9px] text-slate-400">{currentUser.institution_id}</span>
                <button type="button" className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600 hover:text-rose-700" onClick={() => { setOpen(false); onSignOut(); }}>
                  <LogOut size={12} /> End session
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
