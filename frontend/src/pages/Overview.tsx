import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, AlertCircle, RefreshCw } from 'lucide-react';
import { getOverview, getCases } from '../api/endpoints';
import { OverviewData, CaseSummary } from '../types';

const formatINR = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

const statusLabel = (value: string) =>
  value.replace(/[_-]+/g, ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    try {
      const [overviewResult, caseResult] = await Promise.all([getOverview(), getCases()]);
      setOverview(overviewResult);
      setCases(caseResult);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load cases from the API.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const onAuthChanged = () => { void load(true); };
    window.addEventListener('auth-changed', onAuthChanged);
    return () => window.removeEventListener('auth-changed', onAuthChanged);
  }, [load]);

  const openMoneyFlow = (caseId: string) =>
    navigate(`/money-flow?case=${encodeURIComponent(caseId)}`);

  if (loading) {
    return <div className="surface p-8 text-sm text-slate-500">Loading cases from the ledger…</div>;
  }

  if (error || !overview) {
    return (
      <section className="surface p-6">
        <div className="flex items-start gap-3 text-rose-800">
          <AlertCircle size={18} className="mt-0.5" />
          <div className="flex-1"><div className="font-semibold">Case data unavailable</div><p className="mt-1 text-sm">{error || 'The API returned no overview data.'}</p></div>
        </div>
        <button type="button" onClick={() => void load(true)} className="mt-4 inline-flex items-center gap-2 rounded border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50"><RefreshCw size={14} /> Retry</button>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <article className="surface p-4">
          <div className="text-xs text-slate-500">Cases in ledger</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">{overview.cases_available.toLocaleString('en-IN')}</div>
        </article>
        <article className="surface p-4">
          <div className="text-xs text-slate-500">Transactions in scope</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">{overview.transactions_processed.toLocaleString('en-IN')}</div>
        </article>
        <article className="surface p-4">
          <div className="text-xs text-slate-500">Ledger validation</div>
          <div className={`mt-1 text-xl font-semibold ${overview.ledger_valid ? 'text-emerald-800' : 'text-rose-700'}`}>{statusLabel(overview.validation_status)}</div>
        </article>
      </section>

      <section className="surface overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Investigation cases</h2>
            <p className="mt-1 text-xs text-slate-500">Select a real row from the current local ledger to follow its funds.</p>
          </div>
          <button type="button" onClick={() => void load(true)} disabled={refreshing} className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50">
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>

        {cases.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">No cases were returned by the API for this session.</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {cases.map((item) => (
              <div key={item.case_id} className={`grid grid-cols-1 gap-3 px-4 py-4 md:grid-cols-[minmax(0,1fr)_auto_auto_auto] md:items-center ${selectedCaseId === item.case_id ? 'bg-emerald-50/60' : 'bg-white'}`}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-slate-900">{item.case_id}</span>
                    <span className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-600">{statusLabel(item.status)}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{item.transaction_count.toLocaleString('en-IN')} linked transactions · Reported {new Date(item.reported_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })}</div>
                </div>
                <div className="text-sm font-semibold tabular-nums text-slate-900">{formatINR(item.reported_amount_inr)}</div>
                <div className="text-xs text-slate-500">{item.priority_band === 'UNSCORED' ? 'Not scored' : `Priority ${item.priority_band.toLowerCase()}`}</div>
                <button type="button" onClick={() => openMoneyFlow(item.case_id)} className="inline-flex items-center justify-center gap-2 rounded-md bg-[#174b3b] px-3 py-2 text-xs font-semibold text-white hover:bg-[#0f3d2f]">
                  Follow money <ArrowRight size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">Local synthetic ledger only. Reported amount is not confirmed loss or legally recoverable funds.</div>
      </section>
    </div>
  );
};

export default Overview;
