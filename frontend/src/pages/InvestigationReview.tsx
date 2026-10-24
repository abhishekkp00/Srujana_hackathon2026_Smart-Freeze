import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  FileText,
  UserCheck,
  Activity,
  Layers,
  History,
  Info,
} from 'lucide-react';
import { getInvestigationPriorityScores } from '../api/endpoints';
import { PriorityScoreData } from '../types';
import { StatCard } from '../components/common/StatCard';

export const InvestigationReview: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialCase = searchParams.get('case') || '';

  const [allScores, setAllScores] = useState<PriorityScoreData[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(initialCase);
  const [activeScore, setActiveScore] = useState<PriorityScoreData | null>(null);
  const [loading, setLoading] = useState(true);

  // Load all case scores
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const scores = await getInvestigationPriorityScores();
        setAllScores(scores);

        const requestedCase = searchParams.get('case');
        const current = scores.find((s) => s.case_id === requestedCase)
          || scores.find((s) => s.case_id === selectedCaseId)
          || scores[0]
          || null;
        setActiveScore(current);
        setSelectedCaseId(current?.case_id ?? '');
        if (current?.case_id && current.case_id !== requestedCase) {
          setSearchParams({ case: current.case_id }, { replace: true });
        }

      } catch (err) {
        console.error('Failed to load investigation priority data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();

    const handleAuthChange = () => {
      fetchData();
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => window.removeEventListener('auth-changed', handleAuthChange);
  }, []);

  // Update active score when selection changes
  const handleSelectCase = (caseId: string) => {
    setSelectedCaseId(caseId);
    setSearchParams({ case: caseId });
    const match = allScores.find((s) => s.case_id === caseId);
    if (match) {
      setActiveScore(match);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Banner & Case Triage Switcher */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-rose-600 font-semibold text-xs tracking-wider uppercase mb-1">
            <ShieldAlert className="w-4 h-4" />
            <span>Investigative Triage Support</span>
          </div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">
            Explainable Investigation Priority Scoring
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Combines behavioural anomalies (B), transaction-trail complexity (T), and contextual evidence (H) into an auditable heuristic.
          </p>
        </div>

        <div className="flex items-center space-x-3 bg-slate-50 border border-slate-200 px-4 py-2 rounded-xl">
          <label className="text-xs font-semibold text-slate-600">Select Case to Audit:</label>
          <select
            value={selectedCaseId}
            onChange={(e) => handleSelectCase(e.target.value)}
            className="bg-transparent text-xs font-bold text-slate-900 focus:outline-none cursor-pointer"
          >
            {allScores.map((s) => (
              <option key={s.case_id} value={s.case_id}>
                {s.case_id} — Score: {s.final_score?.toFixed(1) || 'N/A'} ({s.priority_band})
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
      ) : activeScore ? (
        <>
          {/* Top Score Summary Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard
              label="Investigation Priority Score"
              value={activeScore.final_score !== null ? `${activeScore.final_score.toFixed(1)} / 100` : 'UNSCORED'}
              subtext="Provisional formula S = 0.40B + 0.40T + 0.20H"
              icon={Activity}
              badge={{
                text: activeScore.priority_band,
                variant:
                  activeScore.priority_band === 'CRITICAL'
                    ? 'danger'
                    : activeScore.priority_band === 'HIGH'
                    ? 'warning'
                    : 'info',
              }}
            />
            <StatCard
              label="Evidence Coverage"
              value={`${(activeScore.evidence_coverage * 100).toFixed(0)}%`}
              subtext={
                activeScore.missing_components.length > 0
                  ? `Missing: ${activeScore.missing_components.join(', ')}`
                  : 'All 3 components fully available'
              }
              icon={CheckCircle2}
              badge={{
                text: activeScore.status,
                variant: activeScore.status === 'SCORED' ? 'success' : 'warning',
              }}
            />
            <StatCard
              label="Reported Case Amount"
              value={`₹${activeScore.reported_amount_inr.toLocaleString('en-IN')}`}
              subtext={`Reported Date: ${activeScore.reported_date}`}
              icon={FileText}
            />
            <StatCard
              label="Audit Records"
              value={`${activeScore.supporting_transaction_ids.length} txs`}
              subtext={`Across ${activeScore.supporting_account_ids.length} internal & external entities`}
              icon={Layers}
            />
          </div>

          {/* Component Score Triad (B, T, H) */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Component B: Behavioural Anomalies */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <span className="text-xs font-bold text-slate-700 uppercase flex items-center">
                  <Activity className="w-3.5 h-3.5 mr-1.5 text-teal-600" />
                  B: Behavioural Anomaly
                </span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  Weight: {activeScore.component_b.weight * 100}%
                </span>
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {activeScore.component_b.score !== null ? `${activeScore.component_b.score} / 100` : 'N/A'}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{activeScore.component_b.description}</p>
              {activeScore.component_b.subfactors && (
                <div className="pt-2 border-t border-slate-100 space-y-1 text-[11px] text-slate-600">
                  <div className="flex justify-between">
                    <span>Rapid pass-through (&lt;2h):</span>
                    <span className="font-mono font-semibold">{activeScore.component_b.subfactors.rapid_movement_pts || 0} pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Amount deviation from baseline:</span>
                    <span className="font-mono font-semibold">{activeScore.component_b.subfactors.amount_deviation_pts || 0} pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Intermediary drain rate:</span>
                    <span className="font-mono font-semibold">{activeScore.component_b.subfactors.drain_pts || 0} pts</span>
                  </div>
                </div>
              )}
            </div>

            {/* Component T: Transaction Trail Evidence */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <span className="text-xs font-bold text-slate-700 uppercase flex items-center">
                  <Layers className="w-3.5 h-3.5 mr-1.5 text-sky-600" />
                  T: Transaction-Trail
                </span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  Weight: {activeScore.component_t.weight * 100}%
                </span>
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {activeScore.component_t.score !== null ? `${activeScore.component_t.score} / 100` : 'N/A'}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{activeScore.component_t.description}</p>
              {activeScore.component_t.subfactors && (
                <div className="pt-2 border-t border-slate-100 space-y-1 text-[11px] text-slate-600">
                  <div className="flex justify-between">
                    <span>Graph layering depth:</span>
                    <span className="font-mono font-semibold">{activeScore.component_t.subfactors.graph_depth_pts || 0} pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Structuring / fan-out branching:</span>
                    <span className="font-mono font-semibold">{activeScore.component_t.subfactors.fan_out_pts || 0} pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cash ATM withdrawal disruption:</span>
                    <span className="font-mono font-semibold">{activeScore.component_t.subfactors.withdrawal_pts || 0} pts</span>
                  </div>
                </div>
              )}
            </div>

            {/* Component H: Historical / Contextual */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <span className="text-xs font-bold text-slate-700 uppercase flex items-center">
                  <History className="w-3.5 h-3.5 mr-1.5 text-amber-600" />
                  H: Historical / Context
                </span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                  Weight: {activeScore.component_h.weight * 100}%
                </span>
              </div>
              <div className="text-2xl font-bold text-slate-900">
                {activeScore.component_h.score !== null ? `${activeScore.component_h.score} / 100` : 'N/A'}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{activeScore.component_h.description}</p>
              {activeScore.component_h.subfactors && (
                <div className="pt-2 border-t border-slate-100 space-y-1 text-[11px] text-slate-600">
                  <div className="flex justify-between">
                    <span>Suspected status ratio:</span>
                    <span className="font-mono font-semibold">{activeScore.component_h.subfactors.suspected_status_pts || 0} pts</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Reported loss magnitude scale:</span>
                    <span className="font-mono font-semibold">{activeScore.component_h.subfactors.amount_scale_pts || 0} pts</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Factors Driving Priority: Escalating vs. Mitigating */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-rose-800 flex items-center">
                <AlertTriangle className="w-4 h-4 mr-2 text-rose-600" />
                Priority Escalating Factors ({activeScore.positive_factors.length})
              </h3>
              <div className="space-y-2">
                {activeScore.positive_factors.length > 0 ? (
                  activeScore.positive_factors.map((pf, idx) => (
                    <div key={idx} className="p-3 bg-rose-50/60 border border-rose-100 rounded-lg text-xs text-rose-900">
                      • {pf}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400">No high-risk escalating factors detected in trail.</p>
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-teal-800 flex items-center">
                <CheckCircle2 className="w-4 h-4 mr-2 text-teal-600" />
                Mitigating Indicators ({activeScore.mitigating_factors.length})
              </h3>
              <div className="space-y-2">
                {activeScore.mitigating_factors.length > 0 ? (
                  activeScore.mitigating_factors.map((mf, idx) => (
                    <div key={idx} className="p-3 bg-teal-50/60 border border-teal-100 rounded-lg text-xs text-teal-900">
                      • {mf}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400">No mitigating factors identified for this trail.</p>
                )}
              </div>
            </div>
          </div>

          {/* Data Quality Warnings */}
          {activeScore.data_quality_warnings.length > 0 && (
            <div className="p-5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-2">
              <div className="flex items-center font-bold text-xs uppercase tracking-wide">
                <AlertTriangle className="w-4 h-4 mr-1.5 text-amber-600" />
                Data Quality & Incomplete History Warnings
              </div>
              {activeScore.data_quality_warnings.map((w, idx) => (
                <div key={idx} className="leading-relaxed">
                  [!] {w}
                </div>
              ))}
            </div>
          )}

          {/* Supporting Evidence Provenance */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center">
              <Info className="w-4 h-4 mr-2 text-slate-600" />
              Supporting Evidence Provenance & Entities
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div>
                <span className="font-semibold text-slate-600 block mb-1">
                  Supporting Transactions ({activeScore.supporting_transaction_ids.length}):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {activeScore.supporting_transaction_ids.map((txId) => (
                    <span key={txId} className="px-2 py-0.5 bg-slate-100 text-slate-700 font-mono rounded border border-slate-200">
                      {txId}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="font-semibold text-slate-600 block mb-1">
                  Involved Accounts ({activeScore.supporting_account_ids.length}):
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {activeScore.supporting_account_ids.map((accId) => (
                    <span key={accId} className="px-2 py-0.5 bg-slate-100 text-slate-700 font-mono rounded border border-slate-200">
                      {accId}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Legal Governance Notice */}
          <div className="p-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-700 text-xs flex items-start space-x-3">
            <UserCheck className="w-4 h-4 text-slate-600 flex-shrink-0 mt-0.5" />
            <div className="leading-relaxed font-normal">
              <span className="font-bold">Human Review Mandate:</span> {activeScore.disclaimer}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
