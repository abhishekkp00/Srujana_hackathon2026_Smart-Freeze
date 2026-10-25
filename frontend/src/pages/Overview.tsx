import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Clock3,
  FileSearch,
  RefreshCw,
  ShieldCheck,
  Wallet,
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
import { OverviewData, CaseSummary, TransactionItem } from '../types';
import './Overview.css';

const formatINR = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })};

const formatExactINR = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

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
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }) + ' UTC';
};

const priorityLabel = (value: string) => {
  if (value === 'UNSCORED') return 'Not scored';
  return value.charAt(0) + value.slice(1).toLowerCase();
};

interface DashboardData {
  overview: OverviewData;
  cases: CaseSummary[];
  transactions: TransactionItem[];
  transactionTotal: number;
}

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caseSearch, setCaseSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'OPEN' | 'CLOSED'>('ALL');

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
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || cause?.message || 'Could not load investigation data from FastAPI.');
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

  const openCases = useMemo(
    () => (data?.cases ?? []).filter((item) => isOpenCase(item.status)),
    [data],
  );

  const openExposure = useMemo(
    () => openCases.reduce((total, item) => total + item.reported_amount_inr, 0),
    [openCases],
  );

  const flaggedTransactions = useMemo(
    () => (data?.transactions ?? []).filter((tx) => tx.evidence_status.toLowerCase() === 'suspected_fraud'),
    [data],
  );

  const filteredCases = useMemo(() => {
    const q = caseSearch.trim().toLowerCase();
    return (data?.cases ?? []).filter((item) => {
      const matchesText = !q || item.case_id.toLowerCase().includes(q);
      const matchesStatus = statusFilter === 'ALL'
        || (statusFilter === 'OPEN' && isOpenCase(item.status))
        || (statusFilter === 'CLOSED' && !isOpenCase(item.status));
      return matchesText && matchesStatus;
    });
  }, [data, caseSearch, statusFilter]);

  const exposureChartData = useMemo(
    () => [...(data?.cases ?? [])]
      .sort((a, b) => b.reported_amount_inr - a.reported_amount_inr)
      .slice(0, 6)
      .map((item) => ({
        caseId: item.case_id,
        amount: item.reported_amount_inr,
        amountLabel: formatINR(item.reported_amount_inr),
      })),
    [data],
  );

  const activityChartData = useMemo(() => {
    const perDay = new Map<string, { day: string; transactions: number; amount: number }>();
    for (const tx of data?.transactions ?? []) {
      const date = new Date(tx.timestamp);
      if (Number.isNaN(date.getTime())) continue;
      const key = date.toISOString().slice(0, 10);
      const existing = perDay.get(key) ?? { day: key, transactions: 0, amount: 0 };
      existing.transactions += 1;
      existing.amount += tx.amount_inr;
      perDay.set(key, existing);
    }
    return [...perDay.values()]
      .sort((a, b) => a.day.localeCompare(b.day))
      .slice(-10)
      .map((item) => ({ ...item, label: formatDate(item.day) }));
  }, [data]);

  const recentTransactions = useMemo(
    () => [...(data?.transactions ?? [])]
      .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
      .slice(0, 6),
    [data],
  );

  if (loading) {
    return (
      <div className="sf-dashboard-loading">
        <RefreshCw size={17} className="animate-spin" />
        <span>Loading investigation ledger…</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <section className="sf-dashboard-error">
        <AlertCircle size={19} />
        <div className="sf-dashboard-error-copy">
          <strong>Investigation data unavailable</strong>
          <p>{error || 'FastAPI returned no dashboard data.'}</p>
          <button type="button" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> Retry
          </button>
        </div>
      </section>
    );
  }

  const { overview, cases, transactions, transactionTotal } = data;
  const hasTransactionSample = transactionTotal > transactions.length;

  return (
    <div className="sf-dashboard">
      <section className="sf-dashboard-toolbar">
        <div>
          <div className="sf-dashboard-overline">INVESTIGATION OPERATIONS</div>
          <h2>Good to see the full picture.</h2>
          <p>Review live ledger data, find a case, and follow its money trail.</p>
        </div>
        <button type="button" className="sf-dashboard-refresh" onClick={() => void load(true)} disabled={refreshing}>
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Refresh data
        </button>
      </section>

      <section className="sf-dashboard-kpis" aria-label="Ledger summary">
        <article className="sf-kpi">
          <div className="sf-kpi-top"><span>Open investigations</span><FileSearch size={16} /></div>
          <div className="sf-kpi-value">{openCases.length.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">{overview.cases_requiring_review.toLocaleString('en-IN')} require review by current status rules</div>
        </article>
        <article className="sf-kpi">
          <div className="sf-kpi-top"><span>Reported exposure</span><Wallet size={16} /></div>
          <div className="sf-kpi-value">{formatINR(openExposure)}</div>
          <div className="sf-kpi-foot">Sum of reported amounts for open cases · not confirmed loss</div>
        </article>
        <article className="sf-kpi">
          <div className="sf-kpi-top"><span>Ledger transactions</span><ArrowUpRight size={16} /></div>
          <div className="sf-kpi-value">{overview.transactions_processed.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">Transactions currently visible to this identity</div>
        </article>
        <article className="sf-kpi">
          <div className="sf-kpi-top"><span>Evidence flags</span><ShieldCheck size={16} /></div>
          <div className="sf-kpi-value">{flaggedTransactions.length.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">
            {hasTransactionSample ? `In the latest ${transactions.length} rows returned` : 'Suspected-fraud flags in returned ledger rows'}
          </div>
        </article>
      </section>

      <section className="sf-dashboard-main-grid">
        <article className="sf-dashboard-panel sf-chart-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Reported amount by case</h3>
              <p>Largest reported amounts in the accessible case list</p>
            </div>
            <span className="sf-panel-unit">INR</span>
          </div>
          {exposureChartData.length ? (
            <div className="sf-chart-area">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={exposureChartData} margin={{ top: 12, right: 8, left: 0, bottom: 6 }}>
                  <CartesianGrid stroke="#e9ebe6" strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="caseId" tick={{ fill: '#737a73', fontSize: 10 }} axisLine={{ stroke: '#daddd6' }} tickLine={false} />
                  <YAxis
                    width={52}
                    tick={{ fill: '#737a73', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(value: number) => value >= 100000 ? `₹${(value / 100000).toFixed(value % 100000 ? 1 : 0)}L` : `₹${Math.round(value / 1000)}k`}
                  />
                  <Tooltip
                    cursor={{ fill: '#f0f2ed' }}
                    formatter={(value) => [formatExactINR(Number(value)), 'Reported amount']}
                    labelStyle={{ color: '#242924', fontSize: 12, fontWeight: 600 }}
                    contentStyle={{ border: '1px solid #daddd6', borderRadius: 4, boxShadow: 'none', fontSize: 12 }}
                  />
                  <Bar dataKey="amount" fill="#344c3d" maxBarSize={42} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sf-chart-empty">No reported amounts are available for this identity.</div>
          )}
          <div className="sf-panel-footnote">Reported amounts are not confirmed loss or legally recoverable balances.</div>
        </article>

        <article className="sf-dashboard-panel sf-activity-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Transaction activity</h3>
              <p>Recorded transfers by ledger date</p>
            </div>
            <Clock3 size={16} className="sf-panel-icon" />
          </div>
          {activityChartData.length ? (
            <>
              <div className="sf-activity-total">
                <strong>{activityChartData.reduce((sum, item) => sum + item.transactions, 0).toLocaleString('en-IN')}</strong>
                <span>rows in chart</span>
              </div>
              <div className="sf-activity-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={activityChartData} margin={{ top: 8, right: 4, left: -21, bottom: 2 }}>
                    <CartesianGrid stroke="#e9ebe6" strokeDasharray="3 4" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: '#737a73', fontSize: 9 }} axisLine={{ stroke: '#daddd6' }} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fill: '#737a73', fontSize: 9 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      formatter={(value) => [Number(value), 'Transactions']}
                      labelStyle={{ color: '#242924', fontSize: 11, fontWeight: 600 }}
                      contentStyle={{ border: '1px solid #daddd6', borderRadius: 4, boxShadow: 'none', fontSize: 11 }}
                    />
                    <Bar dataKey="transactions" fill="#b9c6b8" maxBarSize={24} radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="sf-chart-empty">No dated transaction rows are available.</div>
          )}
          <div className="sf-panel-footnote">
            {hasTransactionSample ? `Chart is based on the first ${transactions.length} rows returned by the API.` : 'Each bar is derived from transaction timestamps in the ledger.'}
          </div>
        </article>
      </section>

      <section className="sf-dashboard-lower-grid">
        <article className="sf-dashboard-panel sf-case-panel">
          <div className="sf-panel-heading sf-case-heading">
            <div>
              <h3>Investigation queue</h3>
              <p>{filteredCases.length} of {cases.length} accessible cases</p>
            </div>
            <div className="sf-case-controls">
              <input
                value={caseSearch}
                onChange={(event) => setCaseSearch(event.target.value)}
                placeholder="Find case ID"
                aria-label="Find case ID"
              />
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'ALL' | 'OPEN' | 'CLOSED')} aria-label="Filter cases by status">
                <option value="ALL">All statuses</option>
                <option value="OPEN">Open</option>
                <option value="CLOSED">Closed</option>
              </select>
            </div>
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
                {filteredCases.map((item) => (
                  <tr key={item.case_id} className={selectedCaseId === item.case_id ? 'sf-row-selected' : ''}>
                    <td>
                      <button type="button" className="sf-case-id" onClick={() => openMoneyFlow(item.case_id)}>{item.case_id}</button>
                      <span className="sf-case-date">Reported {formatDate(item.reported_date)}</span>
                    </td>
                    <td className="sf-table-amount">{formatINR(item.reported_amount_inr)}</td>
                    <td>{item.transaction_count.toLocaleString('en-IN')}</td>
                    <td><span className="sf-status-text">{statusLabel(item.status)}</span></td>
                    <td>
                      <button type="button" className="sf-row-action" aria-label={`Open ${item.case_id}`} onClick={() => openMoneyFlow(item.case_id)}>
                        <ArrowRight size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredCases.length === 0 && <div className="sf-case-empty">No cases match these filters.</div>}
          </div>
          <div className="sf-panel-bottom-link">
            <span>Reported amount is a case reference, not a finding of fraud.</span>
            <button type="button" onClick={() => navigate('/money-flow' + (selectedCaseId ? `?case=${encodeURIComponent(selectedCaseId)}` : ''))}>
              Open money flow <ArrowRight size={13} />
            </button>
          </div>
        </article>

        <article className="sf-dashboard-panel sf-recent-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Recent ledger entries</h3>
              <p>Latest timestamps in the returned transaction rows</p>
            </div>
          </div>
          {recentTransactions.length ? (
            <div className="sf-recent-list">
              {recentTransactions.map((tx) => (
                <button key={tx.transaction_id} type="button" className="sf-recent-row" onClick={() => tx.case_id && openMoneyFlow(tx.case_id)}>
                  <span className="sf-recent-mark" />
                  <span className="sf-recent-copy">
                    <strong>{tx.transaction_id}</strong>
                    <span>{tx.from_account} <ArrowRight size={11} /> {tx.to_account}</span>
                    <small>{formatDateTime(tx.timestamp)} · {statusLabel(tx.evidence_status)}</small>
                  </span>
                  <span className="sf-recent-amount">{formatINR(tx.amount_inr)}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="sf-case-empty">No transaction records were returned.</div>
          )}
          <div className="sf-panel-footnote">
            Ledger integrity: <strong className={overview.ledger_valid ? 'sf-ledger-valid' : 'sf-ledger-invalid'}>{statusLabel(overview.validation_status)}</strong>
            {overview.incomplete_history_accounts > 0 && <> · {overview.incomplete_history_accounts} account histories incomplete</>}
          </div>
        </article>
      </section>
    </div>
  );
};

export default Overview;
