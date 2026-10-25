import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Calendar,
  CheckCircle2,
  Clock3,
  Database,
  FileSearch,
  FolderOpen,
  Info,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Wallet,
  X,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getOverview, getCases, getTransactions } from '../api/endpoints';
import { OverviewData, CaseSummary, TransactionItem, DailyActivityPoint } from '../types';
import './Overview.css';

const formatINR = (amount: number) =>
  '₹' + Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 0 });

const formatExactINR = (amount: number) =>
  '₹' + Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const statusLabel = (value: string) =>
  value.replace(/[_-]+/g, ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

const isOpenCase = (status: string) =>
  !['CLOSED', 'RESOLVED', 'COMPLETED', 'DISMISSED'].includes(status.trim().toUpperCase());

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', timeZone: 'UTC' });
};

const formatDateTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return (
    date.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'UTC',
    }) + ' UTC'
  );
};

interface DashboardData {
  overview: OverviewData;
  cases: CaseSummary[];
  transactions: TransactionItem[];
  transactionTotal: number;
}

interface PopoverDetails {
  title: string;
  formula: string;
  sourceTable: string;
  sourceField: string;
  filterApplied: string;
  timeRange: string;
}

const KpiInfoPopover: React.FC<{
  details: PopoverDetails;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}> = ({ details, isOpen, onToggle, onClose }) => {
  return (
    <div className="sf-kpi-with-info" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="sf-info-btn"
        onClick={onToggle}
        aria-label={`Calculation and source details for ${details.title}`}
        aria-expanded={isOpen}
      >
        <Info size={11} />
      </button>

      {isOpen && (
        <div className="sf-info-popover" role="dialog" aria-modal="false">
          <div className="sf-popover-header">
            <strong>{details.title}</strong>
            <button
              type="button"
              className="sf-popover-close"
              onClick={onClose}
              aria-label="Close details"
            >
              <X size={13} />
            </button>
          </div>

          <div className="sf-popover-section">
            <div className="sf-popover-label">Formula / Definition</div>
            <code className="sf-popover-code">{details.formula}</code>
          </div>

          <div className="sf-popover-section">
            <div className="sf-popover-label">Source Record</div>
            <div className="sf-popover-text">
              <code>{details.sourceTable}</code> → <code>{details.sourceField}</code>
            </div>
          </div>

          <div className="sf-popover-section">
            <div className="sf-popover-label">Filter Applied</div>
            <div className="sf-popover-text">{details.filterApplied}</div>
          </div>

          <div className="sf-popover-section">
            <div className="sf-popover-label">Active Time Range</div>
            <div className="sf-popover-text">{details.timeRange}</div>
          </div>
        </div>
      )}
    </div>
  );
};

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & State
  const [globalSearch, setGlobalSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'OPEN' | 'CLOSED'>('ALL');
  const [activePopover, setActivePopover] = useState<string | null>(null);

  // Date Range Controls
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [activePreset, setActivePreset] = useState<string>('ALL');

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [overview, caseList, transactionPage] = await Promise.all([
        getOverview(),
        getCases(),
        getTransactions({ limit: 500, offset: 0 }),
      ]);
      setData({
        overview,
        cases: caseList,
        transactions: transactionPage.items,
        transactionTotal: transactionPage.total,
      });

      // Set initial date boundaries if not already set
      if (overview.earliest_transaction_date && !startDate) {
        setStartDate(overview.earliest_transaction_date);
      }
      if (overview.latest_transaction_date && !endDate) {
        setEndDate(overview.latest_transaction_date);
      }
    } catch (cause: any) {
      setError(
        cause?.response?.data?.detail ||
          cause?.message ||
          'Could not load truthful dashboard data from FastAPI.'
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    void load();
    const onAuthChanged = () => {
      void load(true);
    };
    window.addEventListener('auth-changed', onAuthChanged);
    return () => window.removeEventListener('auth-changed', onAuthChanged);
  }, [load]);

  // Close open popovers on outside click
  useEffect(() => {
    const handleOutsideClick = () => setActivePopover(null);
    window.addEventListener('click', handleOutsideClick);
    return () => window.removeEventListener('click', handleOutsideClick);
  }, []);

  const openMoneyFlow = (caseId: string) =>
    navigate('/money-flow?case=' + encodeURIComponent(caseId));

  const query = globalSearch.trim().toLowerCase();
  const overview = data?.overview;
  const cases = data?.cases ?? [];
  const transactions = data?.transactions ?? [];

  // Filtered transactions by date range
  const filteredTransactions = useMemo(() => {
    if (!startDate && !endDate) return transactions;
    return transactions.filter((tx) => {
      const day = tx.timestamp.slice(0, 10);
      if (startDate && day < startDate) return false;
      if (endDate && day > endDate) return false;
      return true;
    });
  }, [transactions, startDate, endDate]);

  // Filtered cases by date range
  const filteredCasesByDate = useMemo(() => {
    if (!startDate && !endDate) return cases;
    return cases.filter((c) => {
      const day = c.reported_date.slice(0, 10);
      if (startDate && day < startDate) return false;
      if (endDate && day > endDate) return false;
      return true;
    });
  }, [cases, startDate, endDate]);

  // Filtered daily activity points (discrete bars, no interpolation)
  const filteredDailyActivity = useMemo(() => {
    if (!overview?.daily_activity) return [];
    return overview.daily_activity
      .filter((pt) => {
        if (startDate && pt.date < startDate) return false;
        if (endDate && pt.date > endDate) return false;
        return true;
      })
      .map((pt) => ({
        ...pt,
        label: formatDate(pt.date),
      }));
  }, [overview?.daily_activity, startDate, endDate]);

  // Truthful KPI Calculations with Denominators
  const totalTxCount = filteredTransactions.length;
  const suspectedTxCount = useMemo(
    () =>
      filteredTransactions.filter(
        (t) => t.evidence_status.toLowerCase() === 'suspected_fraud'
      ).length,
    [filteredTransactions]
  );
  const legitimateTxCount = totalTxCount - suspectedTxCount;

  const suspectedPct = totalTxCount > 0
    ? ((suspectedTxCount / totalTxCount) * 100).toFixed(1)
    : '0.0';
  const legitimatePct = totalTxCount > 0
    ? ((legitimateTxCount / totalTxCount) * 100).toFixed(1)
    : '0.0';

  const openCases = useMemo(
    () => filteredCasesByDate.filter((item) => isOpenCase(item.status)),
    [filteredCasesByDate]
  );

  const openCasesPct = cases.length > 0
    ? ((openCases.length / cases.length) * 100).toFixed(0)
    : '0';

  const openExposure = useMemo(
    () => openCases.reduce((total, item) => total + item.reported_amount_inr, 0),
    [openCases]
  );

  // Presets handling
  const applyPreset = (preset: string, start?: string, end?: string) => {
    setActivePreset(preset);
    if (start) setStartDate(start);
    else if (overview?.earliest_transaction_date) setStartDate(overview.earliest_transaction_date);

    if (end) setEndDate(end);
    else if (overview?.latest_transaction_date) setEndDate(overview.latest_transaction_date);
  };

  const resetDateFilter = () => {
    setActivePreset('ALL');
    setStartDate(overview?.earliest_transaction_date || '');
    setEndDate(overview?.latest_transaction_date || '');
  };

  const activeRangeText = startDate && endDate
    ? `${formatDate(startDate)} – ${formatDate(endDate)}`
    : 'All Dates in Ledger';

  // Queue table filtered by search and status
  const queueFilteredCases = useMemo(() => {
    return cases.filter((item) => {
      const matchesText = !query || item.case_id.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === 'ALL' ||
        (statusFilter === 'OPEN' && isOpenCase(item.status)) ||
        (statusFilter === 'CLOSED' && !isOpenCase(item.status));
      const inDate =
        (!startDate || item.reported_date.slice(0, 10) >= startDate) &&
        (!endDate || item.reported_date.slice(0, 10) <= endDate);
      return matchesText && matchesStatus && inDate;
    });
  }, [cases, query, statusFilter, startDate, endDate]);

  const recentTransactions = useMemo(
    () =>
      filteredTransactions
        .filter((tx) => {
          if (!query) return true;
          return [
            tx.transaction_id,
            tx.from_account,
            tx.to_account,
            tx.case_id ?? '',
            tx.transaction_type,
            tx.evidence_status,
          ].some((value) => value.toLowerCase().includes(query));
        })
        .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
        .slice(0, 5),
    [filteredTransactions, query]
  );

  if (loading) {
    return (
      <div className="sf-dashboard-loading">
        <RefreshCw size={17} className="animate-spin" />
        <span>Loading verified ledger analysis from FastAPI…</span>
      </div>
    );
  }

  if (error || !data || !overview) {
    return (
      <section className="sf-dashboard-error">
        <AlertCircle size={19} />
        <div className="sf-dashboard-error-copy">
          <strong>Dashboard data unavailable</strong>
          <p>{error || 'FastAPI returned no operational dashboard records.'}</p>
          <button type="button" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> Retry
          </button>
        </div>
      </section>
    );
  }

  const fl = overview.full_ledger;

  return (
    <div className="sf-dashboard">
      {/* 1. Visible Simulated Data Banner with Generator Seed */}
      <aside className="sf-simulated-banner" aria-label="Dataset provenance">
        <div className="sf-banner-left">
          <span className="sf-banner-badge">
            <Database size={11} /> Simulated Data
          </span>
          <span className="sf-seed-badge">Seed: {overview.generator_seed}</span>
          <span className="sf-banner-text">
            Deterministic synthetic banking ledger simulating multi-rail Indian banking (UPI, IMPS, RTGS, Cash ATM). No live accounts or customer PII.
          </span>
        </div>
        <div className="sf-banner-stat">
          Full Closed Ledger: {fl.total_transactions} txs ({fl.legitimate_transactions} legitimate, {fl.suspected_transactions} suspected across {cases.length} cases)
        </div>
      </aside>

      {/* Toolbar */}
      <section className="sf-dashboard-toolbar">
        <div>
          <div className="sf-dashboard-overline">SMART-FREEZE / INVESTIGATION COCKPIT</div>
          <h2>Truthful Ledger Overview</h2>
          <p>
            Complete closed ledger view: full transaction accounting, distinct fraud indicators, and explainable metrics.
          </p>
        </div>

        <div className="sf-dashboard-tools">
          <label className="sf-global-search">
            <Search size={15} />
            <input
              value={globalSearch}
              onChange={(e) => setGlobalSearch(e.target.value)}
              placeholder="Search cases, accounts, txs..."
              aria-label="Search cases, accounts and transactions"
            />
            {globalSearch && (
              <button
                type="button"
                onClick={() => setGlobalSearch('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </label>
          <button
            type="button"
            className="sf-dashboard-refresh"
            onClick={() => void load(true)}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </section>

      {/* 2. Date Range Selector & Presets */}
      <section className="sf-date-range-bar" aria-label="Date range filters">
        <div className="sf-date-presets">
          <span style={{ fontSize: '10px', fontWeight: 650, color: '#6b7280', marginRight: '4px' }}>
            <Calendar size={12} style={{ display: 'inline', verticalAlign: '-1px', marginRight: '3px' }} />
            Period:
          </span>
          <button
            type="button"
            className={`sf-date-preset-btn ${activePreset === 'ALL' ? 'active' : ''}`}
            onClick={() => applyPreset('ALL')}
          >
            All Ledger (Jan 10–26)
          </button>
          <button
            type="button"
            className={`sf-date-preset-btn ${activePreset === 'SCAM' ? 'active' : ''}`}
            onClick={() => applyPreset('SCAM', '2026-01-10', '2026-01-13')}
          >
            Scam Wave (Jan 10–13)
          </button>
          <button
            type="button"
            className={`sf-date-preset-btn ${activePreset === 'REPORTING' ? 'active' : ''}`}
            onClick={() => applyPreset('REPORTING', '2026-01-14', '2026-01-20')}
          >
            Case Reports (Jan 14–20)
          </button>
          <button
            type="button"
            className={`sf-date-preset-btn ${activePreset === 'SETTLEMENT' ? 'active' : ''}`}
            onClick={() => applyPreset('SETTLEMENT', '2026-01-21', '2026-01-26')}
          >
            Settlement (Jan 21–26)
          </button>
        </div>

        <div className="sf-date-inputs">
          <label htmlFor="sf-start-date">From:</label>
          <input
            id="sf-start-date"
            type="date"
            className="sf-date-input"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setActivePreset('CUSTOM');
            }}
          />
          <label htmlFor="sf-end-date">To:</label>
          <input
            id="sf-end-date"
            type="date"
            className="sf-date-input"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setActivePreset('CUSTOM');
            }}
          />
          {(startDate !== overview.earliest_transaction_date || endDate !== overview.latest_transaction_date) && (
            <button
              type="button"
              className="sf-date-reset-btn"
              onClick={resetDateFilter}
              title="Reset to full ledger date range"
            >
              <RotateCcw size={11} /> Reset
            </button>
          )}
        </div>
      </section>

      {/* Row 1: Four Compact KPI Panels with Restrained Pastel Backgrounds & "i" Popovers */}
      <section className="sf-dashboard-kpis" aria-label="Investigation KPIs">
        {/* KPI 1: Open Cases */}
        <article className="sf-kpi sf-kpi-lilac">
          <div className="sf-kpi-top">
            <div className="sf-kpi-top-title">
              <span>Open Cases</span>
              <KpiInfoPopover
                details={{
                  title: 'Open Cases',
                  formula: 'count(cases WHERE status NOT IN ("CLOSED", "RESOLVED", "DISMISSED"))',
                  sourceTable: 'cases.csv',
                  sourceField: 'status, case_id',
                  filterApplied: 'Active investigations requiring triage or tracing',
                  timeRange: activeRangeText,
                }}
                isOpen={activePopover === 'open_cases'}
                onToggle={() => setActivePopover(activePopover === 'open_cases' ? null : 'open_cases')}
                onClose={() => setActivePopover(null)}
              />
            </div>
            <FolderOpen size={16} />
          </div>
          <div className="sf-kpi-value">{openCases.length.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-denominator">
            {openCases.length} of {cases.length} cases = {cases.length ? Math.round((openCases.length / cases.length) * 100) : 0}% open
          </div>
          <div className="sf-kpi-foot">
            Active investigations requiring review &amp; tracing
          </div>
        </article>

        {/* KPI 2: Reported Exposure */}
        <article className="sf-kpi sf-kpi-peach">
          <div className="sf-kpi-top">
            <div className="sf-kpi-top-title">
              <span>Reported Exposure</span>
              <KpiInfoPopover
                details={{
                  title: 'Reported Exposure',
                  formula: 'sum(reported_amount_paise) / 100 for open cases',
                  sourceTable: 'cases.csv',
                  sourceField: 'reported_amount_paise, status',
                  filterApplied: 'status NOT IN ("CLOSED", "RESOLVED", "DISMISSED")',
                  timeRange: activeRangeText,
                }}
                isOpen={activePopover === 'exposure'}
                onToggle={() => setActivePopover(activePopover === 'exposure' ? null : 'exposure')}
                onClose={() => setActivePopover(null)}
              />
            </div>
            <Wallet size={16} />
          </div>
          <div className="sf-kpi-value">{formatINR(openExposure)}</div>
          <div className="sf-kpi-denominator">
            Sum of reported claims across {openCases.length} open cases
          </div>
          <div className="sf-kpi-foot">
            Complainant reported claim · not confirmed loss
          </div>
        </article>

        {/* KPI 3: Transactions in Scope */}
        <article className="sf-kpi sf-kpi-mint">
          <div className="sf-kpi-top">
            <div className="sf-kpi-top-title">
              <span>Transactions in Scope</span>
              <KpiInfoPopover
                details={{
                  title: 'Transactions in Scope',
                  formula: 'count(transactions) in the reconstructed ledger',
                  sourceTable: 'transactions.csv',
                  sourceField: 'transaction_id',
                  filterApplied: 'All ledger records (case-linked + routine background commerce)',
                  timeRange: activeRangeText,
                }}
                isOpen={activePopover === 'total_tx'}
                onToggle={() => setActivePopover(activePopover === 'total_tx' ? null : 'total_tx')}
                onClose={() => setActivePopover(null)}
              />
            </div>
            <ArrowUpRight size={16} />
          </div>
          <div className="sf-kpi-value">{totalTxCount.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-denominator">
            {fl.case_linked_transactions} case-linked + {fl.unlinked_transactions} background
          </div>
          <div className="sf-kpi-foot">
            100% of recorded ledger activity in scope
          </div>
        </article>

        {/* KPI 4: Evidence-Flagged Transactions */}
        <article className="sf-kpi sf-kpi-rose">
          <div className="sf-kpi-top">
            <div className="sf-kpi-top-title">
              <span>Evidence-Flagged</span>
              <KpiInfoPopover
                details={{
                  title: 'Evidence-Flagged Transactions',
                  formula: 'count(transactions WHERE evidence_status = "suspected_fraud")',
                  sourceTable: 'transactions.csv',
                  sourceField: 'evidence_status',
                  filterApplied: 'evidence_status == "suspected_fraud"',
                  timeRange: activeRangeText,
                }}
                isOpen={activePopover === 'suspected_tx'}
                onToggle={() => setActivePopover(activePopover === 'suspected_tx' ? null : 'suspected_tx')}
                onClose={() => setActivePopover(null)}
              />
            </div>
            <ShieldAlert size={16} />
          </div>
          <div className="sf-kpi-value">{suspectedTxCount.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-denominator">
            {suspectedTxCount} of {totalTxCount} = {suspectedPct}%
          </div>
          <div className="sf-kpi-foot">
            Flagged suspicious transfers across active scam waves
          </div>
        </article>
      </section>

      {/* Row 2: Reported Case Amounts (Main Chart) | Transaction Activity Over Time (Secondary Chart) */}
      <section className="sf-dashboard-main-grid" aria-label="Investigation Charts">
        {/* Chart 1: Reported Amount by Case */}
        <article className="sf-dashboard-panel sf-chart-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Reported Amount by Case</h3>
              <p>Disputed loss claims (INR) across accessible cases</p>
            </div>
            <span className="sf-panel-unit">INR IN LAKHS</span>
          </div>

          {cases.length > 0 ? (
            <div className="sf-line-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={cases.map((c) => ({
                    case_id: c.case_id,
                    reported_amount_inr: c.reported_amount_inr,
                    transaction_count: c.transaction_count,
                    status: c.status,
                  }))}
                  margin={{ top: 14, right: 14, left: 0, bottom: 0 }}
                >
                  <CartesianGrid stroke="#f1f2f8" strokeDasharray="3 4" vertical={false} />
                  <XAxis
                    dataKey="case_id"
                    tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'monospace' }}
                    tickLine={false}
                    axisLine={{ stroke: '#e5e7eb' }}
                  />
                  <YAxis
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => '₹' + (val / 100000).toFixed(1) + 'L'}
                  />
                  <Tooltip
                    contentStyle={{
                      border: '1px solid #e2e8f0',
                      borderRadius: 6,
                      fontSize: 11,
                      boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
                    }}
                    formatter={(val) => [formatExactINR(Number(val)), 'Reported Amount']}
                    labelFormatter={(lbl) => `Case: ${lbl}`}
                  />
                  <Bar
                    dataKey="reported_amount_inr"
                    fill="#625ee8"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={44}
                    onClick={(entry: unknown) => {
                      const data = entry as { payload?: { case_id?: string }; case_id?: string };
                      const targetId = data?.payload?.case_id || data?.case_id;
                      if (targetId) openMoneyFlow(targetId);
                    }}
                    cursor="pointer"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sf-chart-empty">No case records available.</div>
          )}

          <div className="sf-panel-footnote">
            Click any case bar to jump directly into its Money Flow investigation graph.
          </div>
        </article>

        {/* Chart 2: Transaction Activity Over Time */}
        <article className="sf-dashboard-panel sf-chart-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Transaction Activity Over Time</h3>
              <p>Discrete daily volume by actual ledger dates</p>
            </div>
            <span className="sf-panel-unit">DAILY BARS</span>
          </div>

          {filteredDailyActivity.some((pt) => pt.total_transactions > 0) ? (
            <div className="sf-line-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={filteredDailyActivity}
                  margin={{ top: 14, right: 14, left: -16, bottom: 0 }}
                >
                  <CartesianGrid stroke="#f1f2f8" strokeDasharray="3 4" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: '#6b7280', fontSize: 9 }}
                    tickLine={false}
                    axisLine={{ stroke: '#e5e7eb' }}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: '#6b7280', fontSize: 9 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      border: '1px solid #e2e8f0',
                      borderRadius: 6,
                      fontSize: 11,
                      boxShadow: '0 4px 12px rgba(0,0,0,0.06)',
                    }}
                    formatter={(val, name) => [
                      `${val} txs`,
                      name === 'suspected_transactions' ? 'Suspected Fraud' : 'Total Activity',
                    ]}
                    labelFormatter={(lbl) => `Date: ${lbl}`}
                  />
                  <Bar
                    dataKey="total_transactions"
                    name="total_transactions"
                    fill="#a5b4fc"
                    radius={[3, 3, 0, 0]}
                    maxBarSize={22}
                  />
                  <Bar
                    dataKey="suspected_transactions"
                    name="suspected_transactions"
                    fill="#ef4444"
                    radius={[3, 3, 0, 0]}
                    maxBarSize={22}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sf-chart-empty">No transactions recorded in selected date range.</div>
          )}

          <div className="sf-panel-footnote">
            Discrete daily bars for actual dates (zero interpolation). Lilac: total volume, Red: suspected fraud.
          </div>
        </article>
      </section>

      {/* Row 3: Investigation Queue (Left) | Recent Ledger Activity (Right) */}
      <section className="sf-dashboard-lower-grid" aria-label="Investigation Queue and Recent Activity">
        {/* Investigation Queue */}
        <article className="sf-dashboard-panel sf-case-panel">
          <div className="sf-panel-heading sf-case-heading">
            <div>
              <h3>Investigation Queue</h3>
              <p>
                {queueFilteredCases.length} of {cases.length} accessible cases
              </p>
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'ALL' | 'OPEN' | 'CLOSED')}
              aria-label="Filter cases by status"
              className="sf-status-filter"
            >
              <option value="ALL">All statuses</option>
              <option value="OPEN">Open cases</option>
              <option value="CLOSED">Closed cases</option>
            </select>
          </div>
          <div className="sf-case-table-wrap">
            <table className="sf-case-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Reported amount</th>
                  <th>Transactions</th>
                  <th>Status</th>
                  <th aria-label="Action" />
                </tr>
              </thead>
              <tbody>
                {queueFilteredCases.map((item) => (
                  <tr
                    key={item.case_id}
                    className={selectedCaseId === item.case_id ? 'sf-row-selected' : ''}
                  >
                    <td>
                      <button
                        type="button"
                        className="sf-case-id"
                        onClick={() => openMoneyFlow(item.case_id)}
                      >
                        {item.case_id}
                      </button>
                      <span className="sf-case-date">
                        Reported {formatDate(item.reported_date)}
                      </span>
                    </td>
                    <td className="sf-table-amount">{formatINR(item.reported_amount_inr)}</td>
                    <td>{item.transaction_count.toLocaleString('en-IN')}</td>
                    <td>
                      <span className="sf-status-text">{statusLabel(item.status)}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="sf-row-action"
                        aria-label={'Open ' + item.case_id}
                        onClick={() => openMoneyFlow(item.case_id)}
                      >
                        <ArrowRight size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {queueFilteredCases.length === 0 && (
              <div className="sf-case-empty">No cases match this search and status.</div>
            )}
          </div>
          <div className="sf-panel-bottom-link">
            <span>Reported amounts are reference claims, not proven loss.</span>
            <button
              type="button"
              onClick={() =>
                navigate(
                  '/money-flow' + (selectedCaseId ? '?case=' + encodeURIComponent(selectedCaseId) : '')
                )
              }
            >
              Open money flow <ArrowRight size={13} />
            </button>
          </div>
        </article>

        {/* Recent Transactions */}
        <article className="sf-dashboard-panel sf-recent-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Recent Ledger Entries</h3>
              <p>Latest matching transactions</p>
            </div>
            <Clock3 size={16} className="sf-panel-icon" />
          </div>
          {recentTransactions.length ? (
            <div className="sf-recent-list">
              {recentTransactions.map((tx) => (
                <button
                  key={tx.transaction_id}
                  type="button"
                  className="sf-recent-row"
                  onClick={() => tx.case_id && openMoneyFlow(tx.case_id)}
                >
                  <span className="sf-recent-mark" />
                  <span className="sf-recent-copy">
                    <strong>{tx.transaction_id}</strong>
                    <span>
                      {tx.from_account} <ArrowRight size={11} /> {tx.to_account}
                    </span>
                    <small>
                      {formatDateTime(tx.timestamp)} · {statusLabel(tx.evidence_status)}
                    </small>
                  </span>
                  <span className="sf-recent-amount">{formatINR(tx.amount_inr)}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="sf-case-empty">No transactions match in this date range.</div>
          )}
          <div className="sf-panel-footnote">
            Ledger status: <strong className={overview.ledger_valid ? 'sf-ledger-valid' : 'sf-ledger-invalid'}>{statusLabel(overview.validation_status)}</strong>
            {overview.incomplete_history_accounts > 0 && <> · {overview.incomplete_history_accounts} incomplete histories</>}
          </div>
        </article>
      </section>
    </div>
  );
};

export default Overview;
