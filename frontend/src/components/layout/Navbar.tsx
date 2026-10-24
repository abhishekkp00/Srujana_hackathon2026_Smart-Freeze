import React, { useState, useEffect, useRef } from 'react';
import { Search, Bell, Sun, ChevronDown, Check, UserCheck, Shield } from 'lucide-react';

interface Persona {
  id: string;
  name: string;
  role: string;
  initials: string;
  token: string;
  badge: string;
  cases: string;
}

const PERSONAS: Persona[] = [
  {
    id: 'admin',
    name: 'Alex Thorne',
    role: 'Compliance Admin',
    initials: 'AT',
    token: 'dev_token_admin',
    badge: 'Admin Access',
    cases: 'All Cases (*)',
  },
  {
    id: 'investigator_1',
    name: 'Sarah Chen',
    role: 'Lead Investigator',
    initials: 'SC',
    token: 'dev_token_investigator_1',
    badge: 'Investigator',
    cases: 'Cases 001, 002, TP-01..04',
  },
  {
    id: 'investigator_2',
    name: 'Marcus Vance',
    role: 'Investigator',
    initials: 'MV',
    token: 'dev_token_investigator_2',
    badge: 'Investigator',
    cases: 'Case 003 Only (BOLA Demo)',
  },
  {
    id: 'auditor',
    name: 'Priya Nair',
    role: 'External Auditor',
    initials: 'PN',
    token: 'dev_token_auditor',
    badge: 'Auditor',
    cases: 'Read-Only Audit Trail',
  },
  {
    id: 'anonymous',
    name: 'Unauthenticated User',
    role: 'No Role / Public',
    initials: 'AN',
    token: '',
    badge: '401 Unauthorized',
    cases: 'None (Auth Enforcement)',
  },
];

interface NavbarProps {
  title?: string;
  subtitle?: string;
  section?: string;
  selectedCaseId?: string;
  onSelectCaseId?: (caseId: string) => void;
  availableCases?: string[];
}

export const Navbar: React.FC<NavbarProps> = () => {
  const [activeToken, setActiveToken] = useState<string>(() => {
    return localStorage.getItem('smart_freeze_token') ?? 'dev_token_admin';
  });
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentPersona = PERSONAS.find((p) => p.token === activeToken) ?? PERSONAS[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectPersona = (persona: Persona) => {
    if (persona.token) {
      localStorage.setItem('smart_freeze_token', persona.token);
    } else {
      localStorage.removeItem('smart_freeze_token');
    }
    setActiveToken(persona.token);
    setDropdownOpen(false);
    window.dispatchEvent(new Event('auth-changed'));
  };

  return (
    <header className="fh-header">
      {/* Search Bar */}
      <div className="fh-search-container">
        <Search size={16} className="text-slate-400 fh-search-icon" />
        <input
          type="text"
          className="fh-search-input"
          placeholder="Search cases, accounts, transaction reference..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <div className="fh-search-shortcut">
          <span>⌘</span>
          <span>K</span>
        </div>
      </div>

      {/* Right Actions */}
      <div className="fh-header-actions">
        {/* Notifications */}
        <button className="fh-header-btn relative" title="Notifications" aria-label="Notifications">
          <Bell size={18} className="text-slate-600" />
          <span className="fh-notification-dot" />
        </button>

        {/* Theme Toggle */}
        <button className="fh-header-btn" title="Toggle theme" aria-label="Toggle theme">
          <Sun size={18} className="text-slate-600" />
        </button>

        {/* User Profile Pill & Persona Switcher */}
        <div className="relative" ref={dropdownRef}>
          <button
            className="fh-profile-pill"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            aria-expanded={dropdownOpen}
            aria-haspopup="true"
          >
            <div className="fh-profile-avatar">
              <span>{currentPersona.initials}</span>
            </div>
            <div className="fh-profile-info">
              <span className="fh-profile-name">{currentPersona.name}</span>
              <span className="fh-profile-role">{currentPersona.role}</span>
            </div>
            <ChevronDown size={14} className="text-slate-400 ml-1" />
          </button>

          {/* Interactive Dropdown */}
          {dropdownOpen && (
            <div className="fh-persona-dropdown">
              <div className="fh-persona-header">
                <div className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                  <Shield size={13} className="text-emerald-600" />
                  Active Security Persona
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Switching personas triggers live RBAC &amp; BOLA enforcement.
                </div>
              </div>

              <div className="py-1">
                {PERSONAS.map((persona) => {
                  const isSelected = persona.token === activeToken;
                  return (
                    <button
                      key={persona.id}
                      onClick={() => handleSelectPersona(persona)}
                      className={`fh-persona-item ${isSelected ? 'is-selected' : ''}`}
                    >
                      <div className="fh-persona-item-avatar">
                        {persona.initials}
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800">
                            {persona.name}
                          </span>
                          <span className="fh-persona-badge">
                            {persona.badge}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 truncate">
                          {persona.role} · {persona.cases}
                        </div>
                      </div>
                      {isSelected && (
                        <Check size={14} className="text-emerald-600 ml-2 flex-shrink-0" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
