import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowLeftRight, RefreshCw, Zap } from 'lucide-react';
import { getCases, getConsensusLien } from '../api/endpoints';
import { CaseSummary, ConsensusLienData } from '../types';

const inr = (amount: number) => `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const ConsensusLien: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [data, setData] = useState<ConsensusLienData | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCases().then((items) => {
      if (cancelled) return;
      setCases(items);
      const requested = searchParams.get('case') || '';
      if (!items.some((item) => item.case_id === requested)) {
        if (items[0]) setSearchParams({ case: items[0].case_id }, { replace: true });
        else setSearchParams({}, { replace: true });
      }
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load cases.');
    }).finally(() => { if (!cancelled) setLoadingCases(false); });
    return () => { cancelled = true; };
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
    getConsensusLien(selectedCaseId).then((result) => {
      if (!cancelled) setData(result);
    }).catch((cause: any) => {
      if (!cancelled) {
        setData(null);
        setError(cause?.response?.data?.detail || cause?.message || 'Could not calculate tracing results.');
      }
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedCaseId, cases, refreshKey]);

  const sortedCases = useMemo(() => {
    return [...cases].sort((a, b) => {
      if (a.case_id === 'CASE-2026-000') return -1;
      if (b.case_id === 'CASE-2026-000') return 1;
      return a.case_id.localeCompare(b.case_id);
    });
  }, [cases]);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <section className="surface flex flex-wrap items-end justify-between gap-3 p-4">
        <label className="min-w-[260px] flex-1 text-xs font-semibold text-slate-600">
          Case
          <select
            value={selectedCaseId}
            onChange={(event) => setSearchParams(event.target.value ? { case: event.target.value } : {})}
            disabled={loadingCases || cases.length === 0}
            className="mt-1.5 w-full max-w-lg rounded-md border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900"
          >
            {sortedCases.map((item) => (
              <option key={item.case_id} value={item.case_id}>
                {item.case_id === 'CASE-2026-000'
                  ? `⭐ ${item.case_id} · ${inr(item.reported_amount_inr)} (Standard Benchmark: 6 Nodes / 8 Edges)`
                  : `${item.case_id} · ${inr(item.reported_amount_inr)}`}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => navigate(`/money-flow?case=${encodeURIComponent(selectedCaseId)}`)} disabled={!selectedCaseId} className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            <ArrowLeftRight size={14} /> View money flow
          </button>
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading || loadingCases} className="inline-flex items-center gap-2 rounded-md bg-[#174b3b] px-3 py-2.5 text-xs font-semibold text-white hover:bg-[#0f3d2f] disabled:opacity-50">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </section>

      {error && <section className="surface flex items-start gap-2 p-4 text-sm text-rose-800"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</section>}
      {loading ? <section className="surface p-8 text-sm text-slate-500">Calculating Proportional, FIFO and LIBR results…</section> : data ? (
        <>
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <article className="surface p-4"><div className="text-xs text-slate-500">Source transaction</div><div className="mt-1 font-mono text-sm font-semibold text-slate-900">{data.source_transaction_id}</div><div className="mt-1 text-lg font-semibold text-slate-900">{inr(data.source_amount_inr)}</div></article>
            <article className="surface p-4"><div className="text-xs text-slate-500">Estimated retained range</div>{data.consensus_status === 'COMPARABLE' ? <div className="mt-1 text-lg font-semibold text-slate-900">{inr(data.total_lower_bound_inr)} – {inr(data.total_upper_bound_inr)}</div> : <div className="mt-1 text-sm font-semibold text-amber-800">Not comparable</div>}<div className="mt-1 text-xs text-slate-500">Lower and upper method estimates</div></article>
            <article className="surface p-4"><div className="text-xs text-slate-500">Method disagreement</div>{data.consensus_status === 'COMPARABLE' ? <div className="mt-1 text-lg font-semibold text-slate-900">{inr(data.total_disagreement_inr)}</div> : <div className="mt-1 text-sm text-amber-800">Range withheld</div>}<div className="mt-1 text-xs text-slate-500">{data.consensus_status}</div></article>
          </section>

          <section className="surface overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
              <div><h2 className="text-sm font-semibold text-slate-900">Results by account</h2><p className="mt-1 text-xs text-slate-500">Values are recalculated for the selected source transaction.</p></div>
              <span className="rounded border border-slate-200 px-2 py-1 text-[10px] font-semibold text-slate-600">{data.account_liens.length} accounts</span>
            </div>
            {data.account_liens.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
                    <tr><th className="px-4 py-3">Account</th><th className="px-4 py-3">Proportional</th><th className="px-4 py-3">FIFO</th><th className="px-4 py-3">LIBR</th><th className="px-4 py-3">Lower</th><th className="px-4 py-3">Upper</th><th className="px-4 py-3">Difference</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.account_liens.map((row) => (
                      <tr key={row.account_id} className="hover:bg-slate-50">
                        <td className="px-4 py-3"><div className="font-mono font-semibold text-slate-900">{row.account_id}</div><div className="mt-1 text-[10px] text-slate-500">{row.is_external ? 'External counterparty' : row.history_complete ? 'History complete' : 'History incomplete'}</div></td>
                        <td className="px-4 py-3 font-mono text-slate-700">{inr(row.proportional_inr)}</td>
                        <td className="px-4 py-3 font-mono text-slate-700">{inr(row.fifo_inr)}</td>
                        <td className="px-4 py-3 font-mono text-slate-700">{inr(row.libr_inr)}</td>
                        <td className="px-4 py-3 font-mono font-semibold text-slate-800">{inr(row.lower_bound_inr)}</td>
                        <td className="px-4 py-3 font-mono font-semibold text-slate-900">{inr(row.upper_bound_inr)}</td>
                        <td className="px-4 py-3 font-mono text-slate-700">{inr(row.disagreement_inr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="p-6 text-sm text-slate-500">No account-level results were returned.</div>}
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">These are method-dependent tracing estimates—not a legal lien, proof of fraud, or an instruction to freeze funds.</div>
          </section>

          <details className="surface p-4">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">How the three methods differ</summary>
            <div className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
              <div><div className="font-semibold text-slate-900">Proportional</div><p className="mt-1 leading-5 text-slate-600">{data.method_details.proportional.assumption}</p></div>
              <div><div className="font-semibold text-slate-900">FIFO</div><p className="mt-1 leading-5 text-slate-600">{data.method_details.fifo.assumption}</p></div>
              <div><div className="font-semibold text-slate-900">LIBR</div><p className="mt-1 leading-5 text-slate-600">{data.method_details.libr.assumption}</p></div>
            </div>
          </details>
        </>
      ) : !loadingCases ? <section className="surface p-8 text-sm text-slate-500">No case is available in this session.</section> : null}
    </div>
  );
};

export default ConsensusLien;
