import React, { useEffect, useState } from 'react';
import {
  Database,
  CheckCircle2,
  XCircle,
  ShieldCheck,
  Info,
} from 'lucide-react';
import { getDataQuality } from '../api/endpoints';
import { DataQualityData } from '../types';
import { StatCard } from '../components/common/StatCard';
import { Badge } from '../components/common/Badge';

export const DataQuality: React.FC = () => {
  const [dataQuality, setDataQuality] = useState<DataQualityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const data = await getDataQuality();
        setDataQuality(data);
      } catch (err: any) {
        setError(err.message || 'Failed to load data quality audit.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center space-x-2 text-teal-600 font-semibold text-xs tracking-wider uppercase mb-1">
          <Database className="w-4 h-4" />
          <span>Multi-Dataset Audit & Hygiene</span>
        </div>
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">Data Quality, Integrity & Provenance Audit</h2>
        <p className="text-xs text-slate-500 mt-0.5 max-w-3xl leading-relaxed">
          Verifies structural schema conformance, integer-paise representation, and dataset isolation. Public and external benchmark datasets are kept strictly distinct without fabricating missing transactions.
        </p>
      </div>

      {loading ? (
        <div className="space-y-4">
          <div className="h-28 bg-slate-100 rounded-xl animate-pulse border border-slate-200"></div>
          <div className="h-64 bg-slate-100 rounded-xl animate-pulse border border-slate-200"></div>
        </div>
      ) : error || !dataQuality ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-rose-800">
          <div className="font-bold text-sm mb-1">Audit Failed</div>
          <p className="text-xs">{error || 'Unable to retrieve data quality audit.'}</p>
        </div>
      ) : (
        <>
          {/* Audit Summary KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <StatCard
              label="Global Conservation Audit"
              value={dataQuality.ledger_conservation_valid ? 'CONSERVED' : 'FAILED'}
              subtext="Sum(Initial) + Sum(Deposits) - Sum(Withdrawals) = Sum(Final)"
              icon={ShieldCheck}
              badge={{
                text: dataQuality.ledger_conservation_valid ? 'Verified' : 'Violation',
                variant: dataQuality.ledger_conservation_valid ? 'success' : 'danger',
              }}
            />
            <StatCard
              label="Datasets Monitored"
              value={dataQuality.datasets.length}
              subtext="Canonical & optional public benchmarks"
              icon={Database}
            />
            <StatCard
              label="System Operational Health"
              value={dataQuality.overall_status}
              subtext="Core decision-support services active"
              icon={CheckCircle2}
              badge={{ text: 'Operational', variant: 'info' }}
            />
            <StatCard
              label="Ground Truth Status"
              value="STRICTLY ISOLATED"
              subtext="Hidden ground truth excluded from operational paths"
              icon={ShieldCheck}
              badge={{ text: 'Secured', variant: 'success' }}
            />
          </div>

          {/* Dataset Inventory & Hygiene Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-200">
              <h3 className="text-sm font-bold text-slate-900">Supported Dataset Inventory</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Audit of canonical synthetic ledger and optional external benchmark datasets.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[11px] font-semibold">
                  <tr>
                    <th className="py-3 px-4">Dataset Name</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Files</th>
                    <th className="py-3 px-4">Row Count</th>
                    <th className="py-3 px-4">Schema Conformance</th>
                    <th className="py-3 px-4">Audit Notes & Limitations</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {dataQuality.datasets.map((ds, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-4 px-4 font-bold text-slate-800">{ds.dataset_name}</td>
                      <td className="py-4 px-4 text-slate-600">{ds.category}</td>
                      <td className="py-4 px-4">
                        <Badge
                          variant={
                            ds.status === 'VERIFIED_OPERATIONAL'
                              ? 'success'
                              : ds.status === 'SUPPORTED_EXTERNAL'
                              ? 'info'
                              : ds.status === 'ORPHAN_ALERTS'
                              ? 'warning'
                              : 'neutral'
                          }
                          size="sm"
                        >
                          {ds.status}
                        </Badge>
                      </td>
                      <td className="py-4 px-4 font-mono">{ds.file_count}</td>
                      <td className="py-4 px-4 font-mono font-semibold text-slate-800">
                        {ds.total_rows.toLocaleString()}
                      </td>
                      <td className="py-4 px-4">
                        {ds.columns_valid ? (
                          <span className="flex items-center text-emerald-700 font-semibold text-[11px]">
                            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                            Valid
                          </span>
                        ) : (
                          <span className="flex items-center text-slate-400 text-[11px]">
                            <XCircle className="w-3.5 h-3.5 mr-1" />
                            N/A
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-4 text-slate-600 text-[11px] max-w-xs leading-relaxed">
                        {ds.notes}
                        {ds.warnings.length > 0 && (
                          <div className="mt-1 text-amber-700 font-medium">
                            {ds.warnings.map((w, wIdx) => (
                              <div key={wIdx}>[!] {w}</div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Architectural Separation Principles Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 flex items-center">
              <Info className="w-4 h-4 mr-2 text-teal-600" />
              Dataset Separation & Data Hygiene Commitments
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
                <span className="font-bold text-slate-800">No Silent Data Repair:</span>
                <p className="text-slate-600 leading-relaxed">
                  Missing companion journals (such as SynthAML’s missing synthetic_transactions.csv) are reported transparently as orphan alerts and never synthetically fabricated.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
                <span className="font-bold text-slate-800">Ground-Truth Isolation:</span>
                <p className="text-slate-600 leading-relaxed">
                  Controlled ground truth (ground_truth.json) is strictly isolated to post-hoc evaluation runners. Operational tracing and scoring engines are blocked from reading it.
                </p>
              </div>
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-100 space-y-1">
                <span className="font-bold text-slate-800">Multi-Model Separation:</span>
                <p className="text-slate-600 leading-relaxed">
                  Elliptic Bitcoin cryptocurrency UTXO transaction graphs are kept logically distinct from account-based fiat banking ledgers.
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
