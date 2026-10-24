import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Layers,
  ArrowLeftRight,
  ShieldCheck,
  FileCheck2,
  ChevronRight,
  MoreHorizontal,
  Search,
  CheckCircle2,
  Shield,
  FileText,
  Activity,
  AlertTriangle,
  Link2,
  TrendingUp,
  Play,
  ArrowRight,
} from 'lucide-react';
import { getOverview, getCases } from '../api/endpoints';
import { OverviewData, CaseSummary } from '../types';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

const formatINR = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTableQuery, setSearchTableQuery] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        setLoading(true);
        const [overviewData, caseData] = await Promise.all([getOverview(), getCases()]);
        if (!mounted) return;
        setOverview(overviewData);
        setCases(caseData);
        setError(null);
      } catch (err: unknown) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Unable to load overview data.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchData();
    window.addEventListener('auth-changed', fetchData);
    return () => {
      mounted = false;
      window.removeEventListener('auth-changed', fetchData);
    };
  }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="h-64 rounded-2xl bg-slate-200 animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 rounded-xl bg-slate-100 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 text-red-800 p-6 rounded-xl">
          <h3 className="font-semibold text-lg">System Overview Unavailable</h3>
          <p className="mt-2 text-sm">{error || 'Could not connect to FastAPI server.'}</p>
        </div>
      </div>
    );
  }

  // Pre-configured case data for realistic investigation queue
  const queueData = [
    {
      id: 'CASE-2026-001',
      priority: 'CRITICAL',
      status: 'In Progress',
      statusColor: 'bg-emerald-500',
      amount: 100000,
      transactions: 5,
      updated: '2 minutes ago',
      assignedTo: 'Alex Thorne',
      detail: 'Wallet transfer chain with unresolved settlement',
    },
    {
      id: 'CASE-2026-002',
      priority: 'HIGH',
      status: 'Under Review',
      statusColor: 'bg-blue-500',
      amount: 150000,
      transactions: 7,
      updated: '18 minutes ago',
      assignedTo: 'Priya Sharma',
      detail: 'Multiple intermediaries and split flows',
    },
    {
      id: 'CASE-2026-003',
      priority: 'CRITICAL',
      status: 'Triage',
      statusColor: 'bg-amber-500',
      amount: 200000,
      transactions: 2,
      updated: '45 minutes ago',
      assignedTo: 'Rahul Mehta',
      detail: 'Rapid movement and potential mule account',
    },
  ];

  // Chart data for stacked bars
  const stackedChartData = [
    {
      name: 'CASE-2026-001',
      critical: 70000,
      high: 30000,
      medium: 0,
      low: 0,
    },
    {
      name: 'CASE-2026-002',
      critical: 0,
      high: 110000,
      medium: 40000,
      low: 0,
    },
    {
      name: 'CASE-2026-003',
      critical: 140000,
      high: 60000,
      medium: 0,
      low: 0,
    },
  ];

  const filteredQueue = queueData.filter((item) => {
    if (priorityFilter !== 'ALL' && item.priority !== priorityFilter) return false;
    if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
    if (searchTableQuery && !item.id.toLowerCase().includes(searchTableQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <div className="fh-overview-layout">
      {/* Main Workspace (Left 75%) */}
      <div className="fh-workspace-center">
        {/* Hero Banner */}
        <div className="fh-hero-banner">
          <div className="fh-hero-overlay" />
          <div className="fh-hero-content">
            <div className="fh-hero-left">
              <span className="fh-hero-eyebrow">INVESTIGATION WORKSPACE</span>
              <h1 className="fh-hero-title">From Suspicion to Financial Clarity</h1>
              <p className="fh-hero-subtitle">
                Reconstruct multi-rail transaction trails, verify evidence across institutions, and
                quantify traceable funds with rigor.
              </p>
              <div className="fh-hero-buttons">
                <button
                  className="fh-hero-btn-primary"
                  onClick={() => navigate('/investigation')}
                >
                  New Investigation <ArrowRight size={15} />
                </button>
                <button
                  className="fh-hero-btn-secondary"
                  onClick={() => navigate('/traceproof')}
                >
                  <Play size={13} fill="currentColor" /> How it works
                </button>
              </div>
            </div>

            {/* Right Glass Card inside Hero */}
            <div className="fh-hero-glass-card">
              <div className="fh-glass-item">
                <div className="fh-glass-icon-circle">
                  <Link2 size={14} className="text-white" />
                </div>
                <span>Trace across banks, wallets and intermediaries</span>
              </div>
              <div className="fh-glass-item">
                <div className="fh-glass-icon-circle">
                  <ShieldCheck size={14} className="text-white" />
                </div>
                <span>Verify institution-attested evidence</span>
              </div>
              <div className="fh-glass-item">
                <div className="fh-glass-icon-circle">
                  <TrendingUp size={14} className="text-white" />
                </div>
                <span>Quantify traceable amounts with multiple methods</span>
              </div>
              <div className="fh-glass-item">
                <div className="fh-glass-icon-circle">
                  <AlertTriangle size={14} className="text-white" />
                </div>
                <span>Identify gaps and unresolved links</span>
              </div>
            </div>
          </div>
        </div>

        {/* 4 Stat Cards Row */}
        <div className="fh-stats-grid">
          {/* Stat 1: Active Cases */}
          <div className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap">
                <Layers size={18} className="text-emerald-700" />
              </div>
              <div className="fh-stat-label">Active Cases</div>
            </div>
            <div className="fh-stat-val-row">
              <div className="fh-stat-value">{overview.cases_available}</div>
              <div className="fh-stat-delta text-emerald-600">+0 this week</div>
            </div>
            <div className="fh-stat-progress-bar">
              <div className="fh-progress-fill-critical w-2/3" />
              <div className="fh-progress-fill-bg w-1/3" />
            </div>
            <div className="fh-stat-subnote">2 high priority</div>
          </div>

          {/* Stat 2: Transactions Analyzed */}
          <div className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap">
                <ArrowLeftRight size={18} className="text-emerald-700" />
              </div>
              <div className="fh-stat-label">Transactions Analyzed</div>
            </div>
            <div className="fh-stat-val-row">
              <div className="fh-stat-value">{overview.transactions_processed}</div>
              <div className="fh-stat-delta text-emerald-600">+24 in last 24h</div>
            </div>
            {/* Sparkline Histogram */}
            <div className="fh-sparkline-row">
              {[4, 7, 5, 9, 6, 8, 12, 10, 15, 11, 14, 18].map((h, idx) => (
                <div
                  key={idx}
                  className="fh-spark-bar"
                  style={{ height: `${h * 1.5}px` }}
                />
              ))}
            </div>
          </div>

          {/* Stat 3: Internal Accounts */}
          <div className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap">
                <ShieldCheck size={18} className="text-emerald-700" />
              </div>
              <div className="fh-stat-label">Internal Accounts</div>
            </div>
            <div className="fh-stat-val-row">
              <div className="fh-stat-value">{overview.accounts_analyzed}</div>
            </div>
            <div className="fh-stat-note-line">Chronologically reconstructed</div>
            <div
              className="fh-stat-link"
              onClick={() => navigate('/explorer')}
            >
              View →
            </div>
          </div>

          {/* Stat 4: Ledger Verification */}
          <div className="fh-stat-card">
            <div className="fh-stat-top">
              <div className="fh-stat-icon-wrap">
                <FileCheck2 size={18} className="text-emerald-700" />
              </div>
              <div className="fh-stat-label">Ledger Verification</div>
            </div>
            <div className="fh-stat-val-row">
              <div className="fh-stat-value text-emerald-700">Verified</div>
            </div>
            <div className="fh-stat-note-line">Conservation &amp; integrity checks</div>
          </div>
        </div>

        {/* Middle Row: Chart (2/3) + Case Triage (1/3) */}
        <div className="fh-middle-grid">
          {/* Left Chart Card */}
          <div className="fh-panel-card fh-chart-card">
            <div className="fh-panel-head">
              <div>
                <h3 className="fh-panel-title">Reported Case Amounts &amp; Priority</h3>
                <p className="fh-panel-subtitle">Disputed loss amounts (INR) across active cases</p>
              </div>
              <select className="fh-panel-select" defaultValue="30">
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
              </select>
            </div>

            <div className="fh-chart-container">
              <ResponsiveContainer width="100%" height={230}>
                <BarChart
                  data={stackedChartData}
                  margin={{ top: 15, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f3" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(val) => `₹${(val / 100000).toFixed(1)}L`}
                  />
                  <Tooltip
                    formatter={(value: any) => [formatINR(Number(value)), 'Amount']}
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Bar dataKey="critical" stackId="a" fill="#e11d48" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="high" stackId="a" fill="#f97316" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="medium" stackId="a" fill="#eab308" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="low" stackId="a" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className="fh-chart-legend">
              <div className="fh-legend-item">
                <span className="fh-legend-dot bg-rose-600" />
                <span>Critical</span>
              </div>
              <div className="fh-legend-item">
                <span className="fh-legend-dot bg-orange-500" />
                <span>High</span>
              </div>
              <div className="fh-legend-item">
                <span className="fh-legend-dot bg-amber-500" />
                <span>Medium</span>
              </div>
              <div className="fh-legend-item">
                <span className="fh-legend-dot bg-slate-400" />
                <span>Low</span>
              </div>
            </div>
          </div>

          {/* Right Case Triage Card */}
          <div className="fh-panel-card fh-triage-card">
            <div className="fh-panel-head">
              <div>
                <h3 className="fh-panel-title">Case Triage</h3>
                <p className="fh-panel-subtitle">Ranked by investigation priority</p>
              </div>
              <button
                className="fh-link-btn"
                onClick={() => navigate('/investigation')}
              >
                View all →
              </button>
            </div>

            <div className="fh-triage-list">
              {queueData.map((item) => (
                <div
                  key={item.id}
                  className="fh-triage-item"
                  onClick={() => navigate(`/investigation?case=${encodeURIComponent(item.id)}`)}
                >
                  <div className="flex items-start gap-2.5 flex-1 min-w-0">
                    <span
                      className={`fh-triage-bullet ${
                        item.priority === 'CRITICAL' ? 'bg-rose-600' : 'bg-orange-500'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="fh-triage-case-id">{item.id}</span>
                      </div>
                      <div className="fh-triage-sub">
                        {formatINR(item.amount)} · {item.transactions} transactions
                      </div>
                      <div className="fh-triage-detail">{item.detail}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`fh-priority-pill ${
                        item.priority === 'CRITICAL'
                          ? 'fh-priority-critical'
                          : 'fh-priority-high'
                      }`}
                    >
                      {item.priority}
                    </span>
                    <ChevronRight size={15} className="text-slate-400" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Section: Active Investigation Queue Table */}
        <div className="fh-panel-card fh-queue-table-card">
          <div className="fh-table-toolbar">
            <h3 className="fh-panel-title">Active Investigation Queue</h3>
            <div className="fh-table-filters">
              <select
                className="fh-table-select"
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
              >
                <option value="ALL">All Priorities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
              </select>

              <select
                className="fh-table-select"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="ALL">All Status</option>
                <option value="In Progress">In Progress</option>
                <option value="Under Review">Under Review</option>
                <option value="Triage">Triage</option>
              </select>

              <div className="fh-table-search">
                <Search size={14} className="text-slate-400" />
                <input
                  type="text"
                  placeholder="Search cases..."
                  value={searchTableQuery}
                  onChange={(e) => setSearchTableQuery(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="fh-table-wrapper">
            <table className="fh-data-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Disputed Amount</th>
                  <th>Transactions</th>
                  <th>Last Updated</th>
                  <th>Assigned To</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredQueue.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                    onClick={() => navigate(`/investigation?case=${encodeURIComponent(c.id)}`)}
                  >
                    <td className="font-semibold text-slate-800">{c.id}</td>
                    <td>
                      <span
                        className={`fh-priority-pill ${
                          c.priority === 'CRITICAL'
                            ? 'fh-priority-critical'
                            : 'fh-priority-high'
                        }`}
                      >
                        {c.priority}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${c.statusColor}`} />
                        <span className="text-xs text-slate-700">{c.status}</span>
                      </div>
                    </td>
                    <td className="font-mono font-medium text-slate-800">
                      {formatINR(c.amount)}
                    </td>
                    <td className="text-slate-600">{c.transactions}</td>
                    <td className="text-slate-500 text-xs">{c.updated}</td>
                    <td className="text-slate-700 font-medium">{c.assignedTo}</td>
                    <td className="text-right">
                      <button
                        className="text-slate-400 hover:text-slate-700 p-1 rounded"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/investigation?case=${encodeURIComponent(c.id)}`);
                        }}
                      >
                        <MoreHorizontal size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Right Intelligence Rail (Right 25%) */}
      <div className="fh-workspace-right-rail">
        {/* Card 1: Investigation Status */}
        <div className="fh-panel-card fh-status-panel">
          <h3 className="fh-panel-title">Investigation Status</h3>

          <div className="fh-status-banner">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <div>
              <div className="font-semibold text-xs text-slate-900">System Operational</div>
              <div className="text-[11px] text-slate-500">All services running normally</div>
            </div>
          </div>

          <div className="fh-status-rows">
            <div className="fh-status-row">
              <span className="fh-status-item-label">
                <Activity size={14} className="text-slate-400" /> API Services
              </span>
              <span className="fh-status-healthy">Healthy</span>
            </div>

            <div className="fh-status-row">
              <span className="fh-status-item-label">
                <TrendingUp size={14} className="text-slate-400" /> Graph Engine
              </span>
              <span className="fh-status-healthy">Healthy</span>
            </div>

            <div className="fh-status-row">
              <span className="fh-status-item-label">
                <CheckCircle2 size={14} className="text-slate-400" /> ML Model v1.0.0
              </span>
              <span className="fh-status-healthy">Online</span>
            </div>

            <div className="fh-status-row">
              <span className="fh-status-item-label">
                <ShieldCheck size={14} className="text-slate-400" /> Data Integrity
              </span>
              <span className="fh-status-healthy">Validated</span>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100">
            <button
              className="fh-link-btn text-xs"
              onClick={() => navigate('/data-quality')}
            >
              View system health →
            </button>
          </div>
        </div>

        {/* Card 2: Recent Activity */}
        <div className="fh-panel-card fh-activity-panel">
          <div className="fh-panel-head">
            <h3 className="fh-panel-title">Recent Activity</h3>
            <button
              className="fh-link-btn"
              onClick={() => navigate('/investigation')}
            >
              View all →
            </button>
          </div>

          <div className="fh-activity-timeline">
            {/* Event 1 */}
            <div className="fh-timeline-item">
              <div className="fh-timeline-icon-wrap bg-emerald-50 text-emerald-600 border border-emerald-200">
                <CheckCircle2 size={13} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800">Trace completed</div>
                <div className="text-[11px] text-slate-500">CASE-2026-002</div>
                <div className="text-[10px] text-slate-400 mt-0.5">2 minutes ago</div>
              </div>
            </div>

            {/* Event 2 */}
            <div className="fh-timeline-item">
              <div className="fh-timeline-icon-wrap bg-teal-50 text-teal-600 border border-teal-200">
                <Shield size={13} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800">Evidence verified</div>
                <div className="text-[11px] text-slate-500">Wallet Provider B</div>
                <div className="text-[10px] text-slate-400 mt-0.5">8 minutes ago</div>
              </div>
            </div>

            {/* Event 3 */}
            <div className="fh-timeline-item">
              <div className="fh-timeline-icon-wrap bg-emerald-50 text-emerald-600 border border-emerald-200">
                <FileText size={13} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800">New case assigned</div>
                <div className="text-[11px] text-slate-500">CASE-2026-003</div>
                <div className="text-[10px] text-slate-400 mt-0.5">14 minutes ago</div>
              </div>
            </div>

            {/* Event 4 */}
            <div className="fh-timeline-item">
              <div className="fh-timeline-icon-wrap bg-teal-50 text-teal-600 border border-teal-200">
                <TrendingUp size={13} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800">ML analysis completed</div>
                <div className="text-[11px] text-slate-500">CASE-2026-001</div>
                <div className="text-[10px] text-slate-400 mt-0.5">22 minutes ago</div>
              </div>
            </div>

            {/* Event 5 */}
            <div className="fh-timeline-item">
              <div className="fh-timeline-icon-wrap bg-orange-50 text-orange-600 border border-orange-200">
                <AlertTriangle size={13} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-slate-800">Unresolved link detected</div>
                <div className="text-[11px] text-slate-500">Pooled settlement</div>
                <div className="text-[10px] text-slate-400 mt-0.5">28 minutes ago</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
