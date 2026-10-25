import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Clock,
  UserCheck,
  RefreshCw,
  SlidersHorizontal,
  Lock,
  ArrowRight,
  Info,
  Building2,
  FileCheck,
  FileQuestion,
  HelpCircle,
} from 'lucide-react';
import { getCases, getCaseRecommendations } from '../api/endpoints';
import { CaseSummary, CaseRecommendationsData, AccountRecommendation } from '../types';

const inr = (amountPaise: number) => {
  const inrValue = (amountPaise || 0) / 100;
  return `₹${inrValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const ACTION_LABELS: Record<string, { label: string; badgeClass: string; desc: string }> = {
  none: {
    label: 'Tracking only (None)',
    badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
    desc: 'No hold applied. Below de-minimis threshold or no confirmed exposure.',
  },
  lien_core: {
    label: 'Lien core',
    badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    desc: 'Lien set to minimum consensus across Proportional, FIFO, and LIBR.',
  },
  lien_core_plus_margin: {
    label: 'Lien core + margin hold',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
    desc: 'Core lien applied plus time-boxed hold on disagreement margin.',
  },
  outflow_cap: {
    label: 'Outflow cap',
    badgeClass: 'bg-blue-50 text-blue-800 border-blue-200',
    desc: 'Debit transactions restricted to conserve potential stolen funds while allowing legitimate flows.',
  },
  account_level_hold: {
    label: 'Account-level hold',
    badgeClass: 'bg-rose-50 text-rose-800 border-rose-200',
    desc: 'Full account freeze. Requires explicit human analyst authorization.',
  },
};

const REASON_EXPLANATIONS: Record<string, { title: string; desc: string; type: 'harm' | 'rule' | 'invariant' | 'mule' }> = {
  HARM_CLEAN_MAJORITY: {
    title: 'Clean Balance Majority',
    desc: 'Over 50% of the account balance is composed of clean, legitimate funds.',
    type: 'harm',
  },
  HARM_SALARY_INCOME: {
    title: 'Salary / Livelihood Income',
    desc: 'Demonstrated regular payroll or salary inflows protecting essential living expenses.',
    type: 'harm',
  },
  HARM_MERCHANT_COMMERCE: {
    title: 'Active Merchant Commerce',
    desc: 'Frequent commercial counterparty inflows representing working capital.',
    type: 'harm',
  },
  HARM_SCHEDULED_DEBITS: {
    title: 'Scheduled Debits / EMIs',
    desc: 'Upcoming recurring bill debits, EMIs, or loan commitments detected.',
    type: 'harm',
  },
  INVARIANT_CORE_PRESERVED: {
    title: 'Core Lien Preserved',
    desc: 'Harm mitigation factors and submitted documents only discounted the margin. Core remains untouched.',
    type: 'invariant',
  },
  DE_MINIMIS_TRACKING_ONLY: {
    title: 'Below De-Minimis Threshold',
    desc: 'Total stolen exposure across the account is below threshold (tracking only; hold omitted).',
    type: 'rule',
  },
  HIGH_MULE_MARGIN_DISAGREEMENT: {
    title: 'Mule Risk with High Disagreement',
    desc: 'Zero core lien with high method disagreement and elevated mule score triggers time-boxed hold.',
    type: 'mule',
  },
  MANUAL_DOCUMENT_VERIFICATION_REQUIRED: {
    title: 'Analyst Document Review Required',
    desc: 'Uploaded receipts or invoices cannot release holds alone; analyst sign-off is mandatory.',
    type: 'rule',
  },
};

export const RecommendedActions: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [selectedPolicy, setSelectedPolicy] = useState<'conservative' | 'balanced' | 'aggressive'>('balanced');
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [data, setData] = useState<CaseRecommendationsData | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('ALL');

  useEffect(() => {
    let cancelled = false;
    getCases()
      .then((items) => {
        if (cancelled) return;
        setCases(items);
        const requested = searchParams.get('case') || '';
        if (!items.some((item) => item.case_id === requested)) {
          if (items[0]) setSearchParams({ case: items[0].case_id }, { replace: true });
          else setSearchParams({}, { replace: true });
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load cases.');
      })
      .finally(() => {
        if (!cancelled) setLoadingCases(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, setSearchParams]);

  useEffect(() => {
    if (!selectedCaseId || !cases.some((item) => item.case_id === selectedCaseId)) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCaseRecommendations(selectedCaseId, selectedPolicy)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: any) => {
        if (!cancelled) {
          setData(null);
          setError(err?.response?.data?.detail || err?.message || 'Could not fetch case recommendations.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCaseId, selectedPolicy, cases, refreshKey]);

  const filteredRecommendations = useMemo(() => {
    if (!data?.recommendations) return [];
    return data.recommendations.filter((rec) => {
      const matchesSearch =
        rec.account_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rec.reasons.some((r) => r.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesAction = actionFilter === 'ALL' || rec.action === actionFilter;
      return matchesSearch && matchesAction;
    });
  }, [data, searchQuery, actionFilter]);

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {/* 1. Recommend-Only Mandatory Governance Banner */}
      <section className="rounded-lg border-2 border-amber-300 bg-amber-50/90 p-4 shadow-sm" role="alert">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-amber-500 p-2 text-white shrink-0 mt-0.5">
            <ShieldAlert size={22} />
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-amber-900 bg-amber-200/80 px-2 py-0.5 rounded">
                Recommend-Only Governance Notice
              </span>
              <span className="text-xs text-amber-800 font-medium">Decision Support System · Human Approval Required</span>
            </div>
            <p className="text-sm font-semibold text-amber-950">
              Recommendations generated are advisory models for compliance and law-enforcement review.
            </p>
            <p className="text-xs text-amber-900/90 leading-relaxed">
              No automatic account freezes, fund transfers, or releases are executed by this engine. Every consequential
              lien or hold strictly requires independent confirmation by an authorized human investigator in compliance
              with jurisdictional procedural law.
            </p>
          </div>
        </div>
      </section>

      {/* 2. Top Filter and Controls Bar */}
      <section className="surface flex flex-wrap items-center justify-between gap-4 p-4">
        <div className="flex flex-wrap items-center gap-4 flex-1 min-w-[320px]">
          <label className="text-xs font-semibold text-slate-700 min-w-[240px]">
            Active Case
            <select
              value={selectedCaseId}
              onChange={(e) => setSearchParams(e.target.value ? { case: e.target.value } : {})}
              disabled={loadingCases || cases.length === 0}
              className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} · Reported {inr(c.reported_amount_paise || c.reported_amount_inr * 100)}
                </option>
              ))}
            </select>
          </label>

          {/* Policy Dial */}
          <div className="space-y-1">
            <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <SlidersHorizontal size={13} className="text-slate-500" />
              Policy Dial Posture
            </span>
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
              {(['conservative', 'balanced', 'aggressive'] as const).map((dial) => (
                <button
                  key={dial}
                  type="button"
                  onClick={() => setSelectedPolicy(dial)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded capitalize transition-colors ${
                    selectedPolicy === dial
                      ? 'bg-white text-indigo-700 shadow-sm border border-slate-200 font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {dial}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(`/consensus-lien?case=${encodeURIComponent(selectedCaseId)}`)}
            disabled={!selectedCaseId}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
          >
            Compare 3 Methods
          </button>
          <button
            type="button"
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={loading || loadingCases}
            className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </section>

      {/* Error state */}
      {error && (
        <section className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 flex items-start gap-2.5">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-rose-600" />
          <div>
            <div className="font-semibold">Unable to load recommendations</div>
            <div className="text-xs mt-0.5 text-rose-700">{error}</div>
          </div>
        </section>
      )}

      {/* 3. Invariants & Safeguards Strip */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="rounded-md border border-slate-200 bg-white p-3 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
            <CheckCircle2 size={15} className="text-emerald-600 shrink-0" />
            1. Core Lien Invariant
          </div>
          <p className="mt-1 text-[11px] text-slate-600 leading-normal">
            Harm signals and evidence can <strong>only reduce the margin</strong>, never the core consensus lien.
          </p>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-3 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
            <Lock size={15} className="text-amber-600 shrink-0" />
            2. Document Safeguard
          </div>
          <p className="mt-1 text-[11px] text-slate-600 leading-normal">
            Uploaded receipts and salary slips <strong>never release funds alone</strong> without analyst verification.
          </p>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-3 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
            <Building2 size={15} className="text-blue-600 shrink-0" />
            3. Total De-Minimis Rule
          </div>
          <p className="mt-1 text-[11px] text-slate-600 leading-normal">
            Accounts under total stolen de-minimis get <strong>tracking, not a hold</strong> (evaluated on total balance).
          </p>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-3 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
            <UserCheck size={15} className="text-indigo-600 shrink-0" />
            4. Human Gate Invariant
          </div>
          <p className="mt-1 text-[11px] text-slate-600 leading-normal">
            Account-level holds and time-boxed holds <strong>strictly require authorized analyst approval</strong>.
          </p>
        </div>
      </section>

      {/* 4. KPI Metrics Cards */}
      {data && (
        <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className="surface p-3.5">
            <span className="eyebrow block">Suspected Stolen</span>
            <span className="mt-1 block text-lg font-bold text-slate-900">{inr(data.stolen_amount_paise)}</span>
            <span className="text-[10px] text-slate-500">Origin case report</span>
          </div>

          <div className="surface p-3.5">
            <span className="eyebrow block">Joint-Feasible Cap</span>
            <span className="mt-1 block text-lg font-bold text-slate-900">{inr(data.joint_cap_paise)}</span>
            <span className="text-[10px] text-slate-500">Conservation bound</span>
          </div>

          <div className="surface p-3.5 border-l-4 border-l-emerald-500">
            <span className="eyebrow block text-emerald-800">Consensus Core (Min)</span>
            <span className="mt-1 block text-lg font-bold text-emerald-950">{inr(data.total_core_paise)}</span>
            <span className="text-[10px] text-emerald-700">Protected non-disputed</span>
          </div>

          <div className="surface p-3.5 border-l-4 border-l-amber-500">
            <span className="eyebrow block text-amber-800">Method Disagreement</span>
            <span className="mt-1 block text-lg font-bold text-amber-950">{inr(data.total_margin_paise)}</span>
            <span className="text-[10px] text-amber-700">Max minus min range</span>
          </div>

          <div className="surface p-3.5 border-l-4 border-l-indigo-500">
            <span className="eyebrow block text-indigo-800">Recommended Hold</span>
            <span className="mt-1 block text-lg font-bold text-indigo-950">{inr(data.total_held_paise)}</span>
            <span className="text-[10px] text-indigo-700">Core + net margin hold</span>
          </div>

          <div className="surface p-3.5 border-l-4 border-l-rose-500">
            <span className="eyebrow block text-rose-800">Approvals Required</span>
            <span className="mt-1 block text-lg font-bold text-rose-950">{data.requires_human_approval_count}</span>
            <span className="text-[10px] text-rose-700">Accounts needing sign-off</span>
          </div>
        </section>
      )}

      {/* 5. Action Ladder Reference */}
      <section className="surface p-4">
        <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Info size={14} className="text-slate-500" />
          Action Ladder Hierarchy & Progressive Mitigation
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 text-xs">
          <div className="p-2.5 rounded border border-slate-200 bg-slate-50/70">
            <div className="font-semibold text-slate-800 flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-slate-400"></span>
              1. None
            </div>
            <div className="text-[11px] text-slate-600 mt-1">Tracking only; de-minimis total exposure or zero lien.</div>
          </div>
          <div className="p-2.5 rounded border border-emerald-200 bg-emerald-50/70">
            <div className="font-semibold text-emerald-900 flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              2. Lien Core
            </div>
            <div className="text-[11px] text-emerald-800 mt-1">Lien placed only on non-disputed minimum core.</div>
          </div>
          <div className="p-2.5 rounded border border-amber-200 bg-amber-50/70">
            <div className="font-semibold text-amber-900 flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-amber-500"></span>
              3. Lien Core + Margin
            </div>
            <div className="text-[11px] text-amber-800 mt-1">Core lien plus time-boxed hold on uncertainty margin.</div>
          </div>
          <div className="p-2.5 rounded border border-blue-200 bg-blue-50/70">
            <div className="font-semibold text-blue-900 flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-blue-500"></span>
              4. Outflow Cap
            </div>
            <div className="text-[11px] text-blue-800 mt-1">Capped outbound debits; allows routine payments.</div>
          </div>
          <div className="p-2.5 rounded border border-rose-200 bg-rose-50/70">
            <div className="font-semibold text-rose-900 flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-rose-500"></span>
              5. Account Hold
            </div>
            <div className="text-[11px] text-rose-800 mt-1">Full account hold; STRICTLY requires human approval.</div>
          </div>
        </div>
      </section>

      {/* 6. Accounts Recommendation Table */}
      <section className="surface overflow-hidden">
        {/* Table Controls */}
        <div className="p-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold text-slate-900">Per-Account Action Recommendations</h2>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
              Policy: {data?.policy_name || selectedPolicy} · v{data?.policy_version || '1.0.0'}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="Search account or reason..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700"
            >
              <option value="ALL">All Actions ({data?.recommendations.length || 0})</option>
              <option value="none">None / Tracking</option>
              <option value="lien_core">Lien Core</option>
              <option value="lien_core_plus_margin">Lien Core + Margin</option>
              <option value="outflow_cap">Outflow Cap</option>
              <option value="account_level_hold">Account-Level Hold</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-500 text-sm">
            <RefreshCw size={24} className="mx-auto animate-spin mb-3 text-indigo-600" />
            Computing explainable decision recommendations with invariant checks...
          </div>
        ) : filteredRecommendations.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-sm">
            No account recommendations found matching filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">Account ID</th>
                  <th className="px-4 py-3 font-semibold">Balance</th>
                  <th className="px-4 py-3 font-semibold text-emerald-800">Core (Min)</th>
                  <th className="px-4 py-3 font-semibold text-amber-800">Margin</th>
                  <th className="px-4 py-3 font-semibold text-indigo-800">Recommended Hold</th>
                  <th className="px-4 py-3 font-semibold text-slate-700">Free Balance</th>
                  <th className="px-4 py-3 font-semibold">Action Ladder</th>
                  <th className="px-4 py-3 font-semibold">Harm / Mule</th>
                  <th className="px-4 py-3 font-semibold">Approval Gate</th>
                  <th className="px-4 py-3 font-semibold">Reasons & Governance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredRecommendations.map((rec) => {
                  const actionMeta = ACTION_LABELS[rec.action] || ACTION_LABELS.none;
                  return (
                    <tr key={rec.account_id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-4 py-3 font-mono font-bold text-slate-900 whitespace-nowrap">
                        {rec.account_id}
                      </td>

                      <td className="px-4 py-3 font-semibold text-slate-800 whitespace-nowrap">
                        {inr(rec.current_balance_paise)}
                      </td>

                      <td className="px-4 py-3 font-mono font-bold text-emerald-800 whitespace-nowrap">
                        {inr(rec.core)}
                      </td>

                      <td className="px-4 py-3 font-mono text-amber-800 whitespace-nowrap">
                        {inr(rec.margin)}
                      </td>

                      <td className="px-4 py-3 font-mono font-bold text-indigo-900 whitespace-nowrap bg-indigo-50/30">
                        {inr(rec.held_core_paise + rec.held_margin_paise)}
                        {rec.margin_hold_duration_hours && (
                          <span className="block text-[10px] text-amber-700 font-sans font-normal">
                            (margin held {rec.margin_hold_duration_hours}h)
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3 font-mono font-semibold text-emerald-700 whitespace-nowrap">
                        {inr(rec.free)}
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`inline-block px-2.5 py-1 rounded text-[11px] font-semibold border ${actionMeta.badgeClass}`}
                          title={actionMeta.desc}
                        >
                          {actionMeta.label}
                        </span>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200"
                            title={`Harm Score: ${rec.harm_score.toFixed(2)} (measures clean activity & livelihood commitments)`}
                          >
                            Harm: {rec.harm_score.toFixed(2)}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                              rec.mule_score >= 70
                                ? 'bg-rose-50 text-rose-700 border-rose-200'
                                : 'bg-slate-50 text-slate-700 border-slate-200'
                            }`}
                            title={`Mule Score: ${rec.mule_score.toFixed(1)}`}
                          >
                            Mule: {rec.mule_score.toFixed(0)}
                          </span>
                        </div>
                      </td>

                      <td className="px-4 py-3 whitespace-nowrap">
                        {rec.requires_human_approval ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                            <Lock size={11} /> Required
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600">
                            Automated recommendation
                          </span>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1 max-w-sm">
                          {rec.reasons.map((r, idx) => {
                            const exp = REASON_EXPLANATIONS[r];
                            return (
                              <span
                                key={idx}
                                className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                                  exp?.type === 'harm'
                                    ? 'bg-blue-50 text-blue-800 border-blue-200'
                                    : exp?.type === 'invariant'
                                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                    : exp?.type === 'mule'
                                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                                    : 'bg-slate-100 text-slate-700 border-slate-200'
                                }`}
                                title={exp ? `${exp.title}: ${exp.desc}` : r}
                              >
                                {r}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default RecommendedActions;
