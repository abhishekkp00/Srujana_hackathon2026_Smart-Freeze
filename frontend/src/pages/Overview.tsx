import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ArrowLeftRight, BriefcaseBusiness, Activity, ArrowUpRight, Scale, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';
import { getOverview, getCases } from '../api/endpoints';
import { OverviewData, CaseSummary } from '../types';
import { Badge } from '../components/common/Badge';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from 'recharts';

const formatINR = (amount: number) => `₹${Number(amount).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

export const Overview: React.FC = () => {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    return <div className="overview-page"><div><div className="fh-loading-line" /><div className="fh-loading-block mt-5" /></div><div className="overview-stat-grid">{[0,1,2,3].map((n)=><div key={n} className="fh-loading-block" />)}</div></div>;
  }

  if (error || !overview) {
    return <div className="overview-page"><div className="fh-error"><strong>Overview unavailable</strong><p className="mt-2">{error || 'The API did not return overview data.'}</p><p className="mt-2 text-xs">Check that the FastAPI service is running and that this environment is configured for the current API origin.</p></div></div>;
  }

  const caseChartData = cases.map((item) => ({
    name: item.case_id,
    amount: item.reported_amount_inr,
    priority: item.priority_band,
  }));
  const priorityColor: Record<string, string> = {
    CRITICAL: '#ad4c43',
    HIGH: '#b97732',
    MEDIUM: '#b7a16b',
    LOW: '#71917c',
    UNSCORED: '#a7aca1',
  };

  return (
    <div className="overview-page">
      <section className="overview-intro">
        <div>
          <div className="eyebrow">INVESTIGATIONS / CURRENT WORKSPACE</div>
          <h2 className="overview-title">Good work starts with a clear trail.</h2>
          <p className="overview-description">Review recorded activity, follow the movement of funds, and understand where the evidence is strong—or incomplete. FairHold supports analysis; decisions remain with authorized reviewers.</p>
        </div>
        <div className="overview-actions">
          <button className="fh-button-secondary" onClick={() => navigate('/explorer')}><ArrowLeftRight size={14} /> Explore transactions</button>
          <button className="fh-button-primary" onClick={() => navigate('/traceproof')}>Open TraceProof <ArrowUpRight size={14} /></button>
        </div>
      </section>

      <section className="overview-stat-grid" aria-label="Live overview metrics">
        <article className="overview-stat">
          <div className="overview-stat-label"><Users size={14} /> Accounts in scope</div>
          <div className="overview-stat-value">{overview.accounts_analyzed.toLocaleString('en-IN')}</div>
          <div className="overview-stat-note">Accounts in the loaded analytical ledger</div>
        </article>
        <article className="overview-stat">
          <div className="overview-stat-label"><ArrowLeftRight size={14} /> Transactions processed</div>
          <div className="overview-stat-value">{overview.transactions_processed.toLocaleString('en-IN')}</div>
          <div className="overview-stat-note">Recorded events included by the backend</div>
        </article>
        <article className="overview-stat">
          <div className="overview-stat-label"><BriefcaseBusiness size={14} /> Cases available</div>
          <div className="overview-stat-value">{overview.cases_available.toLocaleString('en-IN')}</div>
          <div className="overview-stat-note">{overview.cases_requiring_review.toLocaleString('en-IN')} currently require review</div>
        </article>
        <article className="overview-stat">
          <div className="overview-stat-label"><Activity size={14} /> Ledger status</div>
          <div className="overview-stat-value" style={{fontSize:'clamp(18px, 2vw, 25px)'}}>{String(overview.validation_status)}</div>
          <div className="overview-stat-note">Status returned by the validation service</div>
        </article>
      </section>

      <section className="overview-main-grid">
        <article className="overview-panel">
          <div className="overview-panel-head">
            <div>
              <h3 className="overview-panel-title">Reported amounts by case</h3>
              <p className="overview-panel-caption">Amounts reported for investigation · INR</p>
            </div>
            <span className="overview-panel-meta">{cases.length} case{cases.length === 1 ? '' : 's'}</span>
          </div>
          <div className="overview-chart">
            {caseChartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={caseChartData} margin={{ top: 8, right: 8, left: -12, bottom: 6 }}>
                  <CartesianGrid vertical={false} stroke="#e9ebe3" strokeDasharray="3 5" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fontSize:10, fill:'#8b9288'}} />
                  <YAxis axisLine={false} tickLine={false} tick={{fontSize:10, fill:'#8b9288'}} tickFormatter={(value) => value >= 100000 ? `₹${(value / 100000).toFixed(1)}L` : `₹${(value / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(value) => [formatINR(Number(value)), 'Reported amount']} labelStyle={{fontSize:11, color:'#28382e'}} contentStyle={{background:'#fbfbf8', border:'1px solid #e2e4dc', borderRadius:7, fontSize:11}} />
                  <Bar dataKey="amount" radius={[4,4,0,0]} maxBarSize={48}>
                    {caseChartData.map((entry, index) => <Cell key={`${entry.name}-${index}`} fill={priorityColor[entry.priority] || '#71917c'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="overview-empty">No case amounts are available for this view.</div>}
          </div>
          <div className="overview-panel-caption">Reported amounts are not equivalent to confirmed loss or recoverable funds.</div>
        </article>

        <article className="overview-panel">
          <div className="overview-panel-head">
            <div>
              <h3 className="overview-panel-title">Investigation queue</h3>
              <p className="overview-panel-caption">Open a case to inspect its supporting records.</p>
            </div>
            <button className="fh-icon-button" aria-label="Open all cases" onClick={() => navigate('/investigation')}><ArrowUpRight size={14} /></button>
          </div>
          <div className="overview-case-list">
            {cases.length ? cases.slice(0, 6).map((item) => (
              <button className="overview-case-row" key={item.case_id} onClick={() => navigate(`/investigation?case=${encodeURIComponent(item.case_id)}`)}>
                <div>
                  <div className="overview-case-id">{item.case_id}</div>
                  <div className="overview-case-detail">{item.transaction_count.toLocaleString('en-IN')} transactions · {item.priority_band === 'UNSCORED' ? 'Not scored' : `${item.priority_band.toLowerCase()} priority`}</div>
                </div>
                <div className="overview-case-right">
                  <span className={`overview-priority ${item.priority_band === 'CRITICAL' ? 'is-critical' : item.priority_band === 'HIGH' ? 'is-high' : ''}`}>{item.priority_band}</span>
                  <span className="overview-case-amount">{formatINR(item.reported_amount_inr)}</span>
                </div>
              </button>
            )) : <div className="overview-empty">No cases are available.</div>}
          </div>
          {cases.length > 6 && <button className="fh-button-secondary mt-3 w-full" onClick={() => navigate('/investigation')}>View all cases <ArrowRight size={13} /></button>}
        </article>
      </section>

      <section className="overview-footer-strip">
        <div className="overview-note">
          <div className="overview-note-label"><CheckCircle2 size={13} /> Ledger validation</div>
          <div className="overview-note-value">{String(overview.validation_status)} · Returned by the backend validation status, not a frontend assumption.</div>
        </div>
        <div className="overview-note">
          <div className="overview-note-label"><AlertTriangle size={13} /> Incomplete history</div>
          <div className="overview-note-value">{overview.incomplete_history_accounts.toLocaleString('en-IN')} account(s) with incomplete history. Attribution may be limited.</div>
        </div>
        <div className="overview-note">
          <div className="overview-note-label"><Scale size={13} /> Tracing methodology</div>
          <div className="overview-note-value">Proportional, FIFO and LIBR are separate assumptions. Their outputs are not legal conclusions.</div>
        </div>
      </section>
    </div>
  );
};
