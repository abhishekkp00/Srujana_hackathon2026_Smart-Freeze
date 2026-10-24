import React, { useState, useEffect } from 'react';
import { Shield, CheckCircle2, UserCheck, Lock } from 'lucide-react';

interface NavbarProps {
  title: string;
  subtitle?: string;
  selectedCaseId?: string;
  onSelectCaseId?: (caseId: string) => void;
  availableCases?: string[];
}

interface PersonaOption {
  id: string;
  name: string;
  role: string;
  scope: string;
}

const PERSONAS: PersonaOption[] = [
  { id: 'dev_token_admin', name: 'Alex Thorne', role: 'Compliance Admin', scope: 'All Cases + Audit' },
  { id: 'dev_token_investigator_1', name: 'Sarah Chen', role: 'Investigator', scope: 'CASE-001, CASE-002' },
  { id: 'dev_token_investigator_2', name: 'Marcus Vance', role: 'Investigator', scope: 'CASE-003 Only' },
  { id: 'dev_token_auditor', name: 'Priya Nair', role: 'Auditor', scope: 'Read-Only Audit' },
  { id: 'unauthenticated', name: 'Anonymous', role: 'No Token', scope: 'Denied' },
];

export const Navbar: React.FC<NavbarProps> = ({
  title,
  subtitle,
  selectedCaseId,
  onSelectCaseId,
  availableCases = ['CASE-2026-001', 'CASE-2026-002', 'CASE-2026-003'],
}) => {
  const [activeToken, setActiveToken] = useState<string>(
    localStorage.getItem('smart_freeze_token') || 'dev_token_admin'
  );

  const handlePersonaChange = (token: string) => {
    setActiveToken(token);
    localStorage.setItem('smart_freeze_token', token);
    window.dispatchEvent(new Event('auth-changed'));
  };

  const currentPersona = PERSONAS.find((p) => p.id === activeToken) || PERSONAS[0];

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between flex-shrink-0 z-10 shadow-sm">
      {/* Title & Subtitle */}
      <div>
        <h1 className="text-lg font-bold text-slate-800 tracking-tight flex items-center">
          {title}
        </h1>
        {subtitle && <p className="text-xs text-slate-500 font-medium">{subtitle}</p>}
      </div>

      {/* Controls & Status Badges */}
      <div className="flex items-center space-x-3">
        {/* Case Selector (if provided) */}
        {onSelectCaseId && (
          <div className="flex items-center space-x-2 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200">
            <span className="text-xs font-semibold text-slate-500">Case Focus:</span>
            <select
              value={selectedCaseId}
              onChange={(e) => onSelectCaseId(e.target.value)}
              className="bg-transparent text-xs font-bold text-slate-800 focus:outline-none cursor-pointer"
            >
              {availableCases.map((cid) => (
                <option key={cid} value={cid}>
                  {cid}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Interactive Persona / Auth Context Switcher */}
        <div className="flex items-center space-x-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
          <UserCheck className="w-4 h-4 text-teal-600 flex-shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Active Persona:
            </span>
            <select
              value={activeToken}
              onChange={(e) => handlePersonaChange(e.target.value)}
              className="bg-transparent text-xs font-bold text-slate-800 focus:outline-none cursor-pointer"
            >
              {PERSONAS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.role} — {p.scope})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* BOLA Security Shield Indicator */}
        <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold">
          <Lock className="w-3.5 h-3.5" />
          <span>BOLA & RBAC Active</span>
        </div>

        {/* Ledger Status Badge */}
        <div className="hidden md:flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Ledger Validated</span>
        </div>
      </div>
    </header>
  );
};
