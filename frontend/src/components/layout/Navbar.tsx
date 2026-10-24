import React from 'react';
import { Shield, CheckCircle2 } from 'lucide-react';

interface NavbarProps {
  title: string;
  subtitle?: string;
  selectedCaseId?: string;
  onSelectCaseId?: (caseId: string) => void;
  availableCases?: string[];
}

export const Navbar: React.FC<NavbarProps> = ({
  title,
  subtitle,
  selectedCaseId,
  onSelectCaseId,
  availableCases = ['CASE-2026-001', 'CASE-2026-002', 'CASE-2026-003'],
}) => {
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
      <div className="flex items-center space-x-4">
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

        {/* Ledger Status Badge */}
        <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Ledger Validated</span>
        </div>

        {/* Integrity Mode */}
        <div className="flex items-center space-x-1 px-3 py-1.5 rounded-full bg-slate-100 text-slate-600 text-xs font-medium border border-slate-200">
          <Shield className="w-3.5 h-3.5 text-teal-600" />
          <span>Paise Arithmetic (Exact)</span>
        </div>
      </div>
    </header>
  );
};
