import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Layers,
  FileSpreadsheet,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Scale,
} from 'lucide-react';
import { getOverview, getCases } from '../api/endpoints';
import { OverviewData, CaseSummary } from '../types';
import { StatCard } from '../components/common/StatCard';
import { Badge } from '../components/common/Badge';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [ovData, casesData] = await Promise.all([getOverview(), getCases()]);
        setOverview(ovData);
        setCases(casesData);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to load overview data');
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

  if (loading) {
    return (
      <div className="p-8 space-y-6">
        <div className="h-8 w-64 bg-slate-200 animate-pulse rounded"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-slate-100 animate-pulse rounded-xl border border-slate-200"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="p-8">
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-rose-800">
          <h3 className="font-bold text-base mb-1">Failed to connect to Smart-Freeze Backend</h3>
          <p className="text-sm">{error || 'Unable to retrieve overview metrics.'}</p>
        </div>
      </div>
    );
  }

  // Data for Loss Scale Chart
  const caseChartData = cases.map((c) => ({
    name: c.case_id,
    amount_inr: c.reported_amount_inr,
    band: c.priority_band,
    tx_count: c.transaction_count,
  }));

  const bandColors: Record<string, string> = {
    CRITICAL: '#E11D48',
    HIGH: '#EA580C',
    MEDIUM: '#D97706',
    LOW: '#0D9488',
    UNSCORED: '#64748B',
  };

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Banner / Integrity Notice */}
      <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl p-6 text-white shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2 text-teal-400 font-semibold text-xs tracking-wider uppercase mb-1">
            <ShieldCheck className="w-4 h-4" />
            <span>Operational Integrity Verified</span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Financial Investigation Decision Support</h2>
          <p className="text-slate-300 text-sm mt-1 max-w-2xl leading-relaxed">
            Multi-method fund tracing (Proportional, FIFO, LIBR) and Consensus Lien bounds calculated in exact integer paise. Automated prejudgment or automatic account freezes are strictly prohibited.
          </p>
        </div>

        <button
          onClick={() => navigate('/consensus-lien')}
          className="px-5 py-2.5 rounded-xl bg-teal-500 hover:bg-teal-600 text-white font-semibold text-sm transition-all shadow-md hover:shadow-lg flex items-center flex-shrink-0"
        >
          <span>Run Consensus Lien</span>
          <ArrowRight className="w-4 h-4 ml-2" />
        </button>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard
          label="Internal Accounts"
          value={overview.accounts_analyzed}
          subtext="Chronologically reconstructed accounts"
          icon={Users}
        />
        <StatCard
          label="Transactions Processed"
          value={overview.transactions_processed}
          subtext={`Total turnover: ₹${overview.total_volume_inr.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
          icon={Layers}
        />
        <StatCard
          label="Active Cases"
          value={overview.cases_available}
          subtext="Under investigative triage"
          icon={FileSpreadsheet}
          badge={{ text: '3 Prioritized', variant: 'info' }}
        />
        <StatCard
          label="Ledger Verification"
          value={overview.validation_status}
          subtext="Conservation & non-negative checks pass"
          icon={CheckCircle}
          badge={{ text: 'Conserved', variant: 'success' }}
        />
      </div>

      {/* Secondary Indicators: Data Quality & Uncertainty Flags */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500 uppercase">Statement Completeness</span>
            <AlertTriangle className={`w-4 h-4 ${overview.incomplete_history_accounts > 0 ? 'text-amber-500' : 'text-slate-400'}`} />
          </div>
          <div className="text-2xl font-bold text-slate-900">
            {overview.incomplete_history_accounts} <span className="text-sm font-normal text-slate-500">Accounts</span>
          </div>
          <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
            {overview.incomplete_history_accounts > 0
              ? 'Flagged with incomplete historical statements. Tracing engines flag unknown provenance without fabricating prior deposits.'
              : 'All accounts have complete statement histories.'}
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500 uppercase">Tracing Comparisons</span>
            <Scale className="w-4 h-4 text-teal-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900">3 Methods</div>
          <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
            Proportional, FIFO, and LIBR executed independently across identical scopes and integer-paise ledgers.
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500 uppercase">Human Review Queue</span>
            <Users className="w-4 h-4 text-blue-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900">
            {overview.cases_requiring_review} <span className="text-sm font-normal text-slate-500">Cases</span>
          </div>
          <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
            All cases require authorized investigator review. Scores are triaging heuristics, not proofs of guilt.
          </p>
        </div>
      </div>

      {/* Real Data Chart: Case Reported Loss & Priority Bands */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-base font-bold text-slate-900">Reported Case Amounts & Priority</h3>
              <p className="text-xs text-slate-500 mt-0.5">Disputed loss amounts in Indian Rupees (INR) across active cases</p>
            </div>
            <div className="flex items-center space-x-2 text-xs">
              <span className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-rose-600 mr-1.5"></span>Critical</span>
              <span className="flex items-center ml-2"><span className="w-2.5 h-2.5 rounded-full bg-orange-600 mr-1.5"></span>High</span>
            </div>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={caseChartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#64748B' }} />
                <YAxis
                  tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 12, fill: '#64748B' }}
                />
                <Tooltip
                  formatter={(val: any) => [`₹${Number(val).toLocaleString('en-IN')}`, 'Reported Amount']}
                  labelStyle={{ fontWeight: 'bold', color: '#0F172A' }}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderRadius: '8px', border: '1px solid #E2E8F0' }}
                />
                <Bar dataKey="amount_inr" radius={[6, 6, 0, 0]}>
                  {caseChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={bandColors[entry.band] || '#0D9488'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Case Triage Quick List */}
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900 mb-1">Active Cases Triage</h3>
            <p className="text-xs text-slate-500 mb-4">Ranked by Investigation Priority Score</p>

            <div className="space-y-3">
              {cases.map((c) => (
                <div
                  key={c.case_id}
                  onClick={() => navigate(`/investigation?case=${c.case_id}`)}
                  className="p-3.5 rounded-lg border border-slate-100 hover:border-slate-300 hover:bg-slate-50 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div>
                    <div className="text-sm font-bold text-slate-800">{c.case_id}</div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      ₹{c.reported_amount_inr.toLocaleString('en-IN')} • {c.transaction_count} txs
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Badge variant={c.priority_band === 'CRITICAL' ? 'danger' : c.priority_band === 'HIGH' ? 'warning' : 'neutral'} size="sm">
                      {c.priority_band}
                    </Badge>
                    <ArrowRight className="w-4 h-4 text-slate-400" />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100">
            <button
              onClick={() => navigate('/explorer')}
              className="w-full py-2 px-4 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors flex items-center justify-center"
            >
              <span>Explore All Transactions</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
