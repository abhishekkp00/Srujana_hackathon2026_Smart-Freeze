import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowUpRight,
  Clock3,
  FileSearch,
  RefreshCw,
  Search,
  ShieldCheck,
  Wallet,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getOverview, getCases, getTransactions } from '../api/endpoints';
import { OverviewData, CaseSummary, TransactionItem } from '../types';
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
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }) + ' UTC';
};

interface DashboardData {
  overview: OverviewData;
  cases: CaseSummary[];
  transactions: TransactionItem[];
  transactionTotal: number;
}

interface ActivityPoint {
  day: string;
  label: string;
  transactions: number;
  suspected: number;
  reportedCases: number;
}

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [globalSearch, setGlobalSearch] = useState('');
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
      setError(cause?.response?.data?.detail || cause?.message || 'Could not load dashboard data from FastAPI.');
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
    navigate('/money-flow?case=' + encodeURIComponent(caseId));

  const query = globalSearch.trim().toLowerCase();

  const cases = data?.cases ?? [];
  const transactions = data?.transactions ?? [];

  const openCases = useMemo(
    () => cases.filter((item) => isOpenCase(item.status)),
    [cases],
  );

  const openExposure = useMemo(
    () => openCases.reduce((total, item) => total + item.reported_amount_inr, 0),
    [openCases],
  );

  const flaggedTransactions = useMemo(
    () => transactions.filter((tx) => tx.evidence_status.toLowerCase() === 'suspected_fraud'),
    [transactions],
  );

  const filteredCases = useMemo(() => {
    return cases.filter((item) => {
      const matchesText = !query || item.case_id.toLowerCase().includes(query);
      const matchesStatus = statusFilter === 'ALL'
        || (statusFilter === 'OPEN' && isOpenCase(item.status))
        || (statusFilter === 'CLOSED' && !isOpenCase(item.status));
      return matchesText && matchesStatus;
    });
  }, [cases, query, statusFilter]);

  const exposureChartData = useMemo(
    () => [...cases]
      .sort((a, b) => b.reported_amount_inr - a.reported_amount_inr)
      .slice(0, 6)
      .map((item) => ({
        caseId: item.case_id,
        amount: item.reported_amount_inr,
      })),
    [cases],
  );

  const activityChartData = useMemo(() => {
    const daily = new Map<string, ActivityPoint>();
    const ensureDay = (key: string): ActivityPoint => {
      const existing = daily.get(key);
      if (existing) return existing;
      const point: ActivityPoint = {
        day: key,
        label: formatDate(key),
        transactions: 0,
        suspected: 0,
        reportedCases: 0,
      };
      daily.set(key, point);
      return point;
    };

    for (const tx of transactions) {
      const date = new Date(tx.timestamp);
      if (Number.isNaN(date.getTime())) continue;
      const key = date.toISOString().slice(0, 10);
      const point = ensureDay(key);
      point.transactions += 1;
      if (tx.evidence_status.toLowerCase() === 'suspected_fraud') point.suspected += 1;
    }

    for (const item of cases) {
      const date = new Date(item.reported_date);
      if (Number.isNaN(date.getTime())) continue;
      const key = date.toISOString().slice(0, 10);
      ensureDay(key).reportedCases += 1;
    }

    return [...daily.values()].sort((a, b) => a.day.localeCompare(b.day)).slice(-12);
  }, [transactions, cases]);

  const evidenceStatusData = useMemo(() => {
    const counts = new Map<string, number>();
    for (const tx of transactions) {
      const key = tx.evidence_status || 'unknown';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([status, count]) => ({ status, label: statusLabel(status), count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }, [transactions]);

  const recentTransactions = useMemo(
    () => transactions
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
    [transactions, query],
  );

  if (loading) {
    return (
      <div className="sf-dashboard-loading">
        <RefreshCw size={17} className="animate-spin" />
        <span>Loading investigation data…</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <section className="sf-dashboard-error">
        <AlertCircle size={19} />
        <div className="sf-dashboard-error-copy">
          <strong>Dashboard data unavailable</strong>
          <p>{error || 'FastAPI returned no dashboard data.'}</p>
          <button type="button" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> Retry
          </button>
        </div>
      </section>
    );
  }

  const overview = data.overview;
  const hasTransactionSample = data.transactionTotal > transactions.length;
  const maxEvidenceCount = Math.max(1, ...evidenceStatusData.map((item) => item.count));

  return (
    <div className="sf-dashboard">
      <section className="sf-dashboard-toolbar">
        <div>
          <div className="sf-dashboard-overline">SMART-FREEZE / OPERATIONS</div>
          <h2>Investigation overview</h2>
          <p>Search the ledger or open a case to follow its recorded funds.</p>
        </div>
        <div className="sf-dashboard-tools">
          <label className="sf-global-search">
            <Search size={15} />
            <input
              value={globalSearch}
              onChange={(event) => setGlobalSearch(event.target.value)}
              placeholder="Search cases, accounts, transactions"
              aria-label="Search cases, accounts and transactions"
            />
            {globalSearch && (
              <button type="button" onClick={() => setGlobalSearch('')} aria-label="Clear search">×</button>
            )}
          </label>
          <button type="button" className="sf-dashboard-refresh" onClick={() => void load(true)} disabled={refreshing}>
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </section>

      <section className="sf-dashboard-kpis" aria-label="Investigation summary">
        <article className="sf-kpi sf-kpi-lilac">
          <div className="sf-kpi-top"><span>Open investigations</span><FileSearch size={17} /></div>
          <div className="sf-kpi-value">{openCases.length.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">{overview.cases_requiring_review.toLocaleString('en-IN')} cases require review by status</div>
        </article>
        <article className="sf-kpi sf-kpi-peach">
          <div className="sf-kpi-top"><span>Reported exposure</span><Wallet size={17} /></div>
          <div className="sf-kpi-value">{formatINR(openExposure)}</div>
          <div className="sf-kpi-foot">Open case reported amounts · not confirmed loss</div>
        </article>
        <article className="sf-kpi sf-kpi-mint">
          <div className="sf-kpi-top"><span>Ledger transactions</span><ArrowUpRight size={17} /></div>
          <div className="sf-kpi-value">{overview.transactions_processed.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">Visible to the current demo identity</div>
        </article>
        <article className="sf-kpi sf-kpi-violet">
          <div className="sf-kpi-top"><span>Suspected transactions</span><ShieldCheck size={17} /></div>
          <div className="sf-kpi-value">{flaggedTransactions.length.toLocaleString('en-IN')}</div>
          <div className="sf-kpi-foot">
            {hasTransactionSample ? 'In the first ' + transactions.length + ' rows returned' : 'Rows marked suspected in the ledger'}
          </div>
        </article>
      </section>

      <section className="sf-dashboard-main-grid">
        <article className="sf-dashboard-panel sf-activity-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Transaction activity</h3>
              <p>Ledger rows and case-linked evidence by recorded date</p>
            </div>
            <span className="sf-panel-unit">LAST {activityChartData.length} DATES</span>
          </div>
          {activityChartData.length ? (
            <div className="sf-line-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={activityChartData} margin={{ top: 14, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid stroke="#e8e9f1" strokeDasharray="3 5" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: '#818394', fontSize: 10 }} axisLine={{ stroke: '#e0e1e9' }} tickLine={false} />
                  <YAxis allowDecimals={false} width={30} tick={{ fill: '#818394', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    labelStyle={{ color: '#28283a', fontSize: 12, fontWeight: 600 }}
                    contentStyle={{ border: '1px solid #e0e1e9', borderRadius: 8, boxShadow: '0 6px 22px rgba(30,30,55,.08)', fontSize: 11 }}
                    formatter={(value, name) => [Number(value), String(name)]}
                  />
                  <Legend iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 10, color: '#77798a', paddingTop: 7 }} />
                  <Line type="monotone" dataKey="transactions" name="Transactions" stroke="#625ee8" strokeWidth={2.2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
                  <Line type="monotone" dataKey="suspected" name="Suspected" stroke="#e29a58" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
                  <Line type="monotone" dataKey="reportedCases" name="Cases reported" stroke="#58aa83" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sf-chart-empty">No dated transaction or case records are available.</div>
          )}
          <div className="sf-panel-footnote">
            {hasTransactionSample ? 'Transaction series reflects the first ' + transactions.length + ' rows returned; ' + data.transactionTotal + ' records are available in total.' : 'Each series is computed from transaction timestamps, evidence_status and case report dates.'}
          </div>
        </article>

        <article className="sf-dashboard-panel sf-exposure-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Reported amount by case</h3>
              <p>Accessible cases · sorted by reported amount</p>
            </div>
            <span className="sf-panel-unit">INR</span>
          </div>
          {exposureChartData.length ? (
            <div className="sf-exposure-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={exposureChartData} margin={{ top: 12, right: 8, left: 0, bottom: 3 }}>
                  <CartesianGrid stroke="#e8e9f1" strokeDasharray="3 5" vertical={false} />
                  <XAxis dataKey="caseId" tick={{ fill: '#818394', fontSize: 9 }} axisLine={{ stroke: '#e0e1e9' }} tickLine={false} />
                  <YAxis width={45} tick={{ fill: '#818394', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(value: number) => value >= 100000 ? '₹' + (value / 100000).toFixed(value % 100000 ? 1 : 0) + 'L' : '₹' + Math.round(value / 1000) + 'k'} />
                  <Tooltip
                    cursor={{ fill: '#f0f0fb' }}
                    formatter={(value) => [formatExactINR(Number(value)), 'Reported amount']}
                    labelStyle={{ color: '#28283a', fontSize: 12, fontWeight: 600 }}
                    contentStyle={{ border: '1px solid #e0e1e9', borderRadius: 8, boxShadow: '0 6px 22px rgba(30,30,55,.08)', fontSize: 11 }}
                  />
                  <Bar dataKey="amount" fill="#7773ec" maxBarSize={38} radius={[5, 5, 0, 0]} cursor="pointer" onClick={(entry: any) => { const caseId = entry?.payload?.caseId; if (caseId) openMoneyFlow(String(caseId)); }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="sf-chart-empty">No reported amounts are available for these cases.</div>
          )}
          <div className="sf-panel-footnote">Reported amounts are case references, not confirmed loss or legally recoverable funds.</div>
        </article>
      </section>

      <section className="sf-dashboard-lower-grid">
        <article className="sf-dashboard-panel sf-case-panel">
          <div className="sf-panel-heading sf-case-heading">
            <div>
              <h3>Investigation queue</h3>
              <p>{filteredCases.length} of {cases.length} accessible cases</p>
            </div>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'ALL' | 'OPEN' | 'CLOSED')} aria-label="Filter cases by status" className="sf-status-filter">
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
                      <button type="button" className="sf-row-action" aria-label={'Open ' + item.case_id} onClick={() => openMoneyFlow(item.case_id)}>
                        <ArrowRight size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredCases.length === 0 && <div className="sf-case-empty">No cases match this search and status.</div>}
          </div>
          <div className="sf-panel-bottom-link">
            <span>Reported amounts are not a finding of fraud.</span>
            <button type="button" onClick={() => navigate('/money-flow' + (selectedCaseId ? '?case=' + encodeURIComponent(selectedCaseId) : ''))}>
              Open money flow <ArrowRight size={13} />
            </button>
          </div>
        </article>

        <article className="sf-dashboard-panel sf-evidence-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Evidence status</h3>
              <p>Distribution in the returned transaction rows</p>
            </div>
            <Activity size={16} className="sf-panel-icon" />
          </div>
          <div className="sf-evidence-list">
            {evidenceStatusData.map((item, index) => (
              <div className="sf-evidence-row" key={item.status}>
                <div className="sf-evidence-label"><span>{item.label}</span><strong>{item.count}</strong></div>
                <div className="sf-evidence-track">
                  <div
                    className={'sf-evidence-bar sf-evidence-bar-' + (index % 4)}
                    style={{ width: ((item.count / maxEvidenceCount) * 100) + '%' }}
                  />
                </div>
              </div>
            ))}
            {evidenceStatusData.length === 0 && <div className="sf-case-empty">No evidence labels are available.</div>}
          </div>
          <div className="sf-panel-footnote">
            {hasTransactionSample ? 'Based on ' + transactions.length + ' returned rows of ' + data.transactionTotal + ' total.' : 'Counts use the actual evidence_status field.'}
          </div>
        </article>

        <article className="sf-dashboard-panel sf-recent-panel">
          <div className="sf-panel-heading">
            <div>
              <h3>Recent transactions</h3>
              <p>Latest entries matching the search</p>
            </div>
            <Clock3 size={16} className="sf-panel-icon" />
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
            <div className="sf-case-empty">No transactions match this search.</div>
          )}
          <div className="sf-panel-footnote">
            Ledger integrity: <strong className={overview.ledger_valid ? 'sf-ledger-valid' : 'sf-ledger-invalid'}>{statusLabel(overview.validation_status)}</strong>
            {overview.incomplete_history_accounts > 0 && <> · {overview.incomplete_history_accounts} incomplete account histories</>}
          </div>
        </article>
      </section>
    </div>
  );
};

export default Overview;
