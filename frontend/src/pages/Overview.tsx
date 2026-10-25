import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Layers,
  ArrowLeftRight,
  ShieldCheck,
  FileCheck2,
  ChevronRight,
  Search,
  Activity,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Database,
  BrainCircuit,
} from 'lucide-react';
import { getOverview, getCases, getDataQuality, getMLStatus } from '../api/endpoints';
import { OverviewData, CaseSummary, DataQualityData, MLStatusData } from '../types';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';

const formatINR = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

const formatStatus = (value: string) =>
  value.replace(/[_-]+/g, ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

const priorityColor: Record<string, string> = {
  CRITICAL: '#ad4c43',
  HIGH: '#bd783b',
  MEDIUM: '#ba9c58',
  LOW: '#71917c',
  UNSCORED: '#a7aca1',
};

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [dataQuality, setDataQuality] = useState<DataQualityData | null>(null);
  const [mlStatus, setMlStatus] = useState<MLStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [optionalWarnings, setOptionalWarnings] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    setOptionalWarnings([]);

    try {
      const [overviewResult, casesResult, qualityResult, mlResult] = await Promise.allSettled([
        getOverview(),
        getCases(),
        getDataQuality(),
        getMLStatus(),
      ]);

      if (overviewResult.status !== 'fulfilled') {
        throw overviewResult.reason;
      }
      if (casesResult.status !== 'fulfilled') {
        throw casesResult.reason;
      }

      setOverview(overviewResult.value);
      setCases(casesResult.value);
      setDataQuality(qualityResult.status === 'fulfilled' ? qualityResult.value : null);
      setMlStatus(mlResult.status === 'fulfilled' ? mlResult.value : null);
      setOptionalWarnings([
        ...(qualityResult.status === 'rejected' ? ['Data-quality endpoint did not respond.'] : []),
        ...(mlResult.status === 'rejected' ? ['ML status endpoint did not respond.'] : []),
      ]);
      setLastRefreshedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The API did not return overview data.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
    const onAuthChanged = () => { void fetchData(true); };
    window.addEventListener('auth-changed', onAuthChanged);
    return () => window.removeEventListener('auth-changed', onAuthChanged);
  }, [fetchData]);

  const statusOptions = useMemo(
    () => Array.from(new Set(cases.map((item) => item.status))).sort(),
    [cases],
  );

  const filteredCases = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return cases.filter((item) => {
      if (priorityFilter !== 'ALL' && item.priority_band !== priorityFilter) return false;
      if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
      if (query && !item.case_id.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [cases, priorityFilter, statusFilter, searchQuery]);

  const chartData = useMemo(
    () => cases.map((item) => ({
      name: item.case_id,
      amount: item.reported_amount_inr,
      priority: item.priority_band,
    })),
    [cases],
  );

  const activeCases = cases.filter((item) => !['CLOSED', 'RESOLVED', 'COMPLETED', 'DISMISSED'].includes(item.status.toUpperCase())).length;
  const highPriorityCases = cases.filter((item) => ['CRITICAL', 'HIGH'].includes(item.priority_band)).length;
  const schemaValidatedCount = dataQuality?.datasets.filter((item) => item.columns_valid).length ?? null;
  const schemaDatasetCount = dataQuality?.datasets.length ?? null;

  if (loading) {
    return (
      <div className="fh-overview-layout">
        <div className="fh-workspace-center space-y-4">
          <div className="fh-loading-block" style={{ height: 220 }} />
          <div className="fh-stats-grid">{[0, 1, 2, 3].map((item) => <div key={item} className="fh-loading-block" />)}</div>
          <div className="fh-panel-card"><div className="fh-loading-line" /><div className="fh-loading-block mt-4" style={{ height: 250 }} /></div>
        </div>
        <aside className="fh-workspace-right-rail"><div className="fh-loading-block" style={{ height: 220 }} /></aside>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="fh-panel-card">
        <div className="flex items-start gap-3">
          <AlertTriangle size={19} className="mt-0.5 text-amber-700" />
          <div className="min-w-0 flex-1">
            <h2 className="fh-panel-title">Overview unavailable</h2>
            <p className="fh-panel-subtitle mt-2">{error || 'The API did not return overview data.'}</p>
            <button className="fh-hero-btn-secondary mt-4" type="button" onClick={() => void fetchData(true)} disabled={refreshing}>
              <RefreshCw size={13} /> Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fh-overview-layout">
      <div className="fh-workspace-center">
        <section className="fh-hero-banner">
          <div className="fh-hero-overlay" />
          <div className="fh-hero-content">
            <div className="fh-hero-left">
              <span className="fh-hero-eyebrow">INVESTIGATION WORKSPACE</span>
              <h2 className="fh-hero-title">Follow the evidence, not assumptions.</h2>
              <p className="fh-hero-subtitle">
                Start from a case-linked source transaction, inspect later account movements and commingling context,
                then compare Proportional, FIFO and LIBR attribution ranges. This demonstration uses local synthetic ledger records, not live bank feeds.
              </p>
              <div className="fh-hero-buttons">
                <button
                  className="fh-hero-btn-primary"
                  type="button"
                  onClick={() => navigate(cases[0] ? `/money-flow?case=${encodeURIComponent(cases[0].case_id)}` : '/money-flow')}
                >
                  Reconstruct money flow <ArrowRight size={15} />
                </button>
                <button className="fh-hero-btn-secondary" type="button" onClick={() => navigate('/explorer')}>
                  Inspect ledger records <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="fh-stats-grid" aria-label="Metrics returned by the backend">
          <article className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap"><Layers size={18} className="text-emerald-700" /></div>
              <div className="fh-stat-label">Cases available</div>
            </div>
            <div className="fh-stat-val-row"><div className="fh-stat-value">{overview.cases_available.toLocaleString('en-IN')}</div></div>
            <div className="fh-stat-note-line">{overview.cases_requiring_review.toLocaleString('en-IN')} require review by the backend's current status rule</div>
          </article>

          <article className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap"><ArrowLeftRight size={18} className="text-emerald-700" /></div>
              <div className="fh-stat-label">Transactions in scope</div>
            </div>
            <div className="fh-stat-val-row"><div className="fh-stat-value">{overview.transactions_processed.toLocaleString('en-IN')}</div></div>
            <div className="fh-stat-note-line">Recorded entries returned by the selected identity's scope</div>
          </article>

          <article className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap"><ShieldCheck size={18} className="text-emerald-700" /></div>
              <div className="fh-stat-label">Accounts in scope</div>
            </div>
            <div className="fh-stat-val-row"><div className="fh-stat-value">{overview.accounts_analyzed.toLocaleString('en-IN')}</div></div>
            <div className="fh-stat-note-line">{overview.incomplete_history_accounts.toLocaleString('en-IN')} account(s) have incomplete history</div>
          </article>

          <article className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap"><FileCheck2 size={18} className="text-emerald-700" /></div>
              <div className="fh-stat-label">Ledger validation</div>
            </div>
            <div className="fh-stat-val-row">
              <div className="fh-stat-value" style={{ fontSize: 'clamp(18px, 2vw, 25px)' }}>{formatStatus(overview.validation_status)}</div>
            </div>
            <div className="fh-stat-note-line">Status returned by the ledger validation service</div>
          </article>
        </section>

        <section className="fh-middle-grid">
          <article className="fh-panel-card fh-chart-card">
            <div className="fh-panel-head">
              <div>
                <h3 className="fh-panel-title">Reported case amounts</h3>
                <p className="fh-panel-subtitle">Reported amounts for the cases visible to this identity · INR</p>
              </div>
              <span className="text-[10px] font-mono text-slate-500">{chartData.length} records</span>
            </div>
            <div className="fh-chart-container">
              {chartData.length ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={chartData} margin={{ top: 12, right: 8, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8ece8" />
                    <XAxis dataKey="name" axisLine={{ stroke: '#dce3dc' }} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={(value) => value >= 100000 ? `₹${(value / 100000).toFixed(1)}L` : `₹${(value / 1000).toFixed(0)}k`} />
                    <Tooltip formatter={(value) => [formatINR(Number(value)), 'Reported amount']} labelStyle={{ fontWeight: 600, fontSize: 11 }} contentStyle={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 7, fontSize: 11 }} />
                    <Bar dataKey="amount" radius={[4, 4, 0, 0]} maxBarSize={46}>
                      {chartData.map((item) => <Cell key={item.name} fill={priorityColor[item.priority] || priorityColor.UNSCORED} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="py-12 text-center text-xs text-slate-500">No case records are available in this access scope.</div>
              )}
            </div>
            <p className="fh-panel-subtitle">Reported amounts are not confirmed loss or legally recoverable funds.</p>
          </article>

          <article className="fh-panel-card fh-triage-card">
            <div className="fh-panel-head">
              <div>
                <h3 className="fh-panel-title">Investigation triage</h3>
                <p className="fh-panel-subtitle">Priority is derived from backend scoring, when available.</p>
              </div>
              <button className="fh-link-btn" type="button" onClick={() => navigate('/investigation')}>Open queue <ArrowRight size={13} /></button>
            </div>
            <div className="fh-triage-list">
              {cases.slice().sort((a, b) => (b.priority_score ?? -1) - (a.priority_score ?? -1)).slice(0, 6).map((item) => (
                <button key={item.case_id} type="button" className="fh-triage-item w-full text-left" onClick={() => navigate(`/investigation?case=${encodeURIComponent(item.case_id)}`)}>
                  <div className="flex items-start gap-2.5 flex-1 min-w-0">
                    <span className={`fh-triage-bullet ${item.priority_band === 'CRITICAL' ? 'bg-rose-600' : item.priority_band === 'HIGH' ? 'bg-orange-500' : 'bg-slate-400'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="fh-triage-case-id">{item.case_id}</div>
                      <div className="fh-triage-sub">{formatINR(item.reported_amount_inr)} · {item.transaction_count.toLocaleString('en-IN')} transactions</div>
                      <div className="fh-triage-detail">{formatStatus(item.status)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`fh-priority-pill ${item.priority_band === 'CRITICAL' ? 'fh-priority-critical' : item.priority_band === 'HIGH' ? 'fh-priority-high' : ''}`}>{item.priority_band === 'UNSCORED' ? 'UNSCORED' : item.priority_band}</span>
                    <ChevronRight size={15} className="text-slate-400" />
                  </div>
                </button>
              ))}
              {cases.length === 0 && <div className="py-5 text-xs text-slate-500">No cases are visible to this identity.</div>}
            </div>
          </article>
        </section>

        <section className="fh-panel-card fh-queue-table-card">
          <div className="fh-table-toolbar">
            <div>
              <h3 className="fh-panel-title">Investigation queue</h3>
              <p className="fh-panel-subtitle">Values below are read from the authorized cases API.</p>
            </div>
            <div className="fh-table-filters">
              <select className="fh-table-select" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)} aria-label="Filter by priority">
                <option value="ALL">All priorities</option>
                {Array.from(new Set(cases.map((item) => item.priority_band))).sort().map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <select className="fh-table-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter by status">
                <option value="ALL">All statuses</option>
                {statusOptions.map((value) => <option key={value} value={value}>{formatStatus(value)}</option>)}
              </select>
              <div className="fh-table-search">
                <Search size={14} className="text-slate-400" />
                <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search case ID…" aria-label="Search cases" />
              </div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="fh-data-table w-full text-left">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Reported amount</th>
                  <th>Transactions</th>
                  <th>Reported date</th>
                  <th>Priority score</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((item) => (
                  <tr key={item.case_id} className="interactive-row cursor-pointer" onClick={() => navigate(`/investigation?case=${encodeURIComponent(item.case_id)}`)}>
                    <td className="font-mono font-medium">{item.case_id}</td>
                    <td><span className={`fh-priority-pill ${item.priority_band === 'CRITICAL' ? 'fh-priority-critical' : item.priority_band === 'HIGH' ? 'fh-priority-high' : ''}`}>{item.priority_band}</span></td>
                    <td>{formatStatus(item.status)}</td>
                    <td className="font-mono">{formatINR(item.reported_amount_inr)}</td>
                    <td>{item.transaction_count.toLocaleString('en-IN')}</td>
                    <td className="font-mono text-xs">{new Date(item.reported_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })}</td>
                    <td className="font-mono">{item.priority_score == null ? 'Not scored' : item.priority_score.toFixed(1)}</td>
                    <td className="text-right"><button type="button" className="text-slate-400 hover:text-slate-700 p-1 rounded" aria-label={`Open ${item.case_id}`} onClick={(event) => { event.stopPropagation(); navigate(`/investigation?case=${encodeURIComponent(item.case_id)}`); }}><ChevronRight size={15} /></button></td>
                  </tr>
                ))}
                {filteredCases.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-xs text-slate-500">No cases match the selected filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <div className="text-[10px] text-slate-400 flex flex-wrap items-center justify-between gap-2">
          <span>Snapshot refreshed {lastRefreshedAt ?? 'not recorded'} · {overview.system_version}</span>
          <button type="button" className="inline-flex items-center gap-1.5 hover:text-slate-700 disabled:opacity-50" onClick={() => void fetchData(true)} disabled={refreshing}>
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} /> Refresh from API
          </button>
        </div>
      </div>

      <aside className="fh-workspace-right-rail">
        <section className="fh-panel-card fh-status-panel">
          <div className="fh-panel-head">
            <h3 className="fh-panel-title">Service and data status</h3>
            <button type="button" className="fh-link-btn" onClick={() => navigate('/data-quality')}>Details <ArrowRight size={12} /></button>
          </div>
          <div className="fh-status-banner">
            <span className={`w-2.5 h-2.5 rounded-full ${dataQuality?.overall_status === 'HEALTHY' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            <div>
              <div className="font-semibold text-xs text-slate-900">{dataQuality ? formatStatus(dataQuality.overall_status) : 'Status unavailable'}</div>
              <div className="text-[11px] text-slate-500">Data-quality API response</div>
            </div>
          </div>
          <div className="fh-status-rows">
            <div className="fh-status-row">
              <span className="fh-status-item-label"><Activity size={14} className="text-slate-400" /> Ledger</span>
              <span className={overview.ledger_valid ? 'fh-status-healthy' : 'text-rose-700'}>{formatStatus(overview.validation_status)}</span>
            </div>
            <div className="fh-status-row">
              <span className="fh-status-item-label"><Database size={14} className="text-slate-400" /> Schema checks</span>
              <span className="text-right text-xs text-slate-600">{schemaValidatedCount == null || schemaDatasetCount == null ? 'Unavailable' : `${schemaValidatedCount}/${schemaDatasetCount} passed`}</span>
            </div>
            <div className="fh-status-row">
              <span className="fh-status-item-label"><BrainCircuit size={14} className="text-slate-400" /> ML model</span>
              <span className={mlStatus?.status === 'LOADED' && mlStatus.artifact_sha256_verified ? 'fh-status-healthy' : 'text-amber-700'}>
                {mlStatus ? (mlStatus.status === 'LOADED' ? (mlStatus.artifact_sha256_verified ? 'Loaded · hash matched' : 'Loaded · hash not verified') : mlStatus.status) : 'Unavailable'}
              </span>
            </div>
            <div className="fh-status-row">
              <span className="fh-status-item-label"><AlertTriangle size={14} className="text-slate-400" /> Incomplete history</span>
              <span className="text-slate-700">{overview.incomplete_history_accounts.toLocaleString('en-IN')}</span>
            </div>
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <p className="text-[10px] leading-4 text-slate-500">
              Local demonstration ledger and dataset snapshots. No live banking feed is connected.
            </p>
          </div>
          {optionalWarnings.map((warning) => <p key={warning} className="mt-2 text-[10px] text-amber-700">{warning}</p>)}
        </section>

        <section className="fh-panel-card">
          <div className="fh-panel-head">
            <h3 className="fh-panel-title">Review notes</h3>
          </div>
          <div className="space-y-3 text-xs text-slate-600">
            <div className="flex items-start gap-2.5">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-slate-400" />
              <p>Tracing methods use different attribution assumptions. Compare them only within a common source, scope and cutoff.</p>
            </div>
            <div className="flex items-start gap-2.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-slate-400" />
              <p>Reported amounts are not confirmed loss. Incomplete history can limit attribution.</p>
            </div>
            <div className="flex items-start gap-2.5">
              <BrainCircuit size={14} className="mt-0.5 shrink-0 text-slate-400" />
              <p>The card-fraud classifier is trained on a separate European benchmark and is not a bank AML model.</p>
            </div>
          </div>
        </section>
      </aside>
    </div>
  );
};

export default Overview;
