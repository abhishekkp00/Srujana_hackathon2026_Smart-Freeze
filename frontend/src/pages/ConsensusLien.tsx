import React, { useEffect, useState } from 'react';
import {
  Scale,
  Info,
  AlertTriangle,
  FileText,
  FileCheck,
} from 'lucide-react';
import { getConsensusLien, getCases } from '../api/endpoints';
import { ConsensusLienData, CaseSummary } from '../types';
import { StatCard } from '../components/common/StatCard';
import { Badge } from '../components/common/Badge';

export const ConsensusLien: React.FC = () => {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('CASE-2026-001');
  const [lienData, setLienData] = useState<ConsensusLienData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load cases list
  useEffect(() => {
    const fetchCases = async () => {
      try {
        const cList = await getCases();
        setCases(cList);
      } catch (err) {
        console.error('Failed to load cases:', err);
      }
    };
    fetchCases();

    const handleAuthChange = () => {
      fetchCases();
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => window.removeEventListener('auth-changed', handleAuthChange);
  }, []);

  // Load Consensus Lien data for selected case
  useEffect(() => {
    if (!selectedCaseId) return;
    const fetchLien = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getConsensusLien(selectedCaseId);
        setLienData(data);
      } catch (err: any) {
        setError(err.message || 'Failed to calculate Consensus Lien for this case.');
        setLienData(null);
      } finally {
        setLoading(false);
      }
    };
    fetchLien();
  }, [selectedCaseId]);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Banner / Case Focus */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-teal-600 font-semibold text-xs tracking-wider uppercase mb-1">
            <Scale className="w-4 h-4" />
            <span>Multi-Method Tracing Bounds</span>
          </div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Consensus Lien Comparison Engine</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Compares independently computed Proportional, FIFO, and LIBR tracing outcomes to bound fund exposure.
          </p>
        </div>

        {/* Case Switcher */}
        <div className="flex items-center space-x-3 bg-slate-50 border border-slate-200 px-4 py-2 rounded-xl">
          <label className="text-xs font-semibold text-slate-600">Select Fraud Case:</label>
          <select
            value={selectedCaseId}
            onChange={(e) => setSelectedCaseId(e.target.value)}
            className="bg-transparent text-xs font-bold text-slate-900 focus:outline-none cursor-pointer"
          >
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {c.case_id} (₹{(c.reported_amount_inr / 1000).toFixed(0)}k)
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="h-28 bg-slate-100 rounded-xl animate-pulse border border-slate-200"></div>
          <div className="h-64 bg-slate-100 rounded-xl animate-pulse border border-slate-200"></div>
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-rose-800">
          <div className="flex items-center font-bold text-sm mb-1">
            <AlertTriangle className="w-4 h-4 mr-2" />
            Method Incomparability or Data Error
          </div>
          <p className="text-xs leading-relaxed">{error}</p>
        </div>
      ) : lienData ? (
        <>
          {/* Summary KPIs: Lower Bound, Upper Bound, Disagreement */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard
              label="Source Fraud Lot"
              value={`₹${lienData.source_amount_inr.toLocaleString('en-IN')}`}
              subtext={`Origin Tx: ${lienData.source_transaction_id}`}
              icon={FileText}
            />
            <StatCard
              label="Lower Method Bound (min)"
              value={`₹${lienData.total_lower_bound_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
              subtext="Minimum retained across methods"
              icon={Scale}
              badge={{ text: 'Conservative', variant: 'success' }}
            />
            <StatCard
              label="Upper Method Bound (max)"
              value={`₹${lienData.total_upper_bound_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
              subtext="Maximum retained across methods"
              icon={Scale}
              badge={{ text: 'Ceiling', variant: 'warning' }}
            />
            <StatCard
              label="Method Disagreement Range"
              value={`₹${lienData.total_disagreement_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
              subtext="Upper bound minus Lower bound"
              icon={AlertTriangle}
              badge={{
                text: lienData.total_disagreement_paise === 0 ? 'Full Consensus' : 'Divergent',
                variant: lienData.total_disagreement_paise === 0 ? 'success' : 'danger',
              }}
            />
          </div>

          {/* Three-Method Comparison Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Account-Level Consensus Lien Breakdown</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Comparison of exact integer-paise allocations calculated by Proportional, FIFO, and LIBR.
                </p>
              </div>
              <Badge variant="primary" size="sm">
                Status: {lienData.consensus_status}
              </Badge>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[11px] font-semibold">
                  <tr>
                    <th className="py-3 px-4">Account ID</th>
                    <th className="py-3 px-4">Proportional (INR)</th>
                    <th className="py-3 px-4">FIFO (INR)</th>
                    <th className="py-3 px-4">LIBR (INR)</th>
                    <th className="py-3 px-4 bg-teal-50/50 text-teal-800">Lower Bound</th>
                    <th className="py-3 px-4 bg-teal-50/50 text-teal-800">Upper Bound</th>
                    <th className="py-3 px-4 text-rose-700">Disagreement (Δ)</th>
                    <th className="py-3 px-4">Audit Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {lienData.account_liens.map((l) => (
                    <tr key={l.account_id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-800">
                        {l.account_id}
                        {l.is_external && <span className="ml-1 text-[10px] text-amber-600 font-semibold">(External Outflow)</span>}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-700">
                        ₹{l.proportional_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-700">
                        ₹{l.fifo_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-700">
                        ₹{l.libr_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4 font-mono font-bold text-emerald-800 bg-teal-50/30">
                        ₹{l.lower_bound_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4 font-mono font-bold text-sky-900 bg-teal-50/30">
                        ₹{l.upper_bound_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4 font-mono font-semibold text-rose-600">
                        ₹{l.disagreement_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-3.5 px-4">
                        {!l.history_complete ? (
                          <Badge variant="warning" size="sm">Incomplete History</Badge>
                        ) : (
                          <Badge variant="success" size="sm">Complete</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Structured Divergence & Mathematical Explanation */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Method Assumptions Panel */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-slate-900 flex items-center">
                <FileCheck className="w-4 h-4 mr-2 text-teal-600" />
                Underlying Algorithm Assumptions
              </h3>
              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="font-bold text-slate-800">Proportional Tracing:</span>
                  <p className="text-slate-600 mt-0.5">{lienData.method_details.proportional.assumption}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="font-bold text-slate-800">First-In, First-Out (FIFO):</span>
                  <p className="text-slate-600 mt-0.5">{lienData.method_details.fifo.assumption}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="font-bold text-slate-800">Lowest Intermediate Balance Rule (LIBR):</span>
                  <p className="text-slate-600 mt-0.5">{lienData.method_details.libr.assumption}</p>
                </div>
              </div>
            </div>

            {/* Narrative Explanation */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold text-slate-900 flex items-center">
                <Info className="w-4 h-4 mr-2 text-sky-600" />
                Consensus & Divergence Explanation
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed font-medium">
                {lienData.explanation.summary}
              </p>

              <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
                {Object.entries(lienData.explanation.account_explanations).map(([aid, expText]) => (
                  <div key={aid} className="text-xs p-2.5 rounded bg-slate-50 border border-slate-100 font-mono text-[11px] text-slate-700 whitespace-pre-line">
                    {expText}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Mandatory Governance Warning */}
          <div className="p-5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start space-x-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              <span className="font-bold">Investigative Estimate Notice:</span> {lienData.governance_notice}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
