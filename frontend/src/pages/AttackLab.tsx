import React, { useEffect, useState } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Crosshair,
  SlidersHorizontal,
  RefreshCw,
  TrendingUp,
  AlertTriangle,
  Info,
  Layers,
  Clock,
  Shuffle,
  Split,
  Building2,
  CheckCircle2,
  Award,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { getAttackLabReport } from '../api/endpoints';
import { AttackLabReportData, PolicyEvaluationSummaryData } from '../types';

const inr = (amount: number) => {
  return `₹${(amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const AttackLab: React.FC = () => {
  const [seed, setSeed] = useState<number>(42);
  const [population, setPopulation] = useState<number>(24);
  const [generations, setGenerations] = useState<number>(15);
  const [data, setData] = useState<AttackLabReportData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPolicyTab, setSelectedPolicyTab] = useState<'policy_v2' | 'policy_v1' | 'defenses_off'>('policy_v2');

  const runExperiment = async (s = seed, p = population, g = generations) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAttackLabReport({ seed: s, population: p, generations: g });
      setData(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to run Attack Lab experiment.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runExperiment(42, 24, 15);
  }, []);

  const chartData = data?.evolution_history.map((h) => ({
    gen: `Gen ${h.generation}`,
    'Best Fitness': Math.round(h.best_fitness),
    'Mean Fitness': Math.round(h.mean_fitness),
    'Escaped (₹)': Math.round(h.best_escaped_rupees),
    'Innocent Held (₹)': Math.round(h.best_innocent_held_rupees),
  })) || [];

  const activeTuningSummary: PolicyEvaluationSummaryData | undefined =
    data?.tuning_comparison[selectedPolicyTab];
  const activeHeldOutSummary: PolicyEvaluationSummaryData | undefined =
    data?.held_out_comparison[selectedPolicyTab];

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {/* 1. Mandatory Governance Banner */}
      <section className="rounded-lg border-2 border-indigo-200 bg-indigo-50/90 p-4 shadow-sm" role="alert">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-indigo-600 p-2 text-white shrink-0 mt-0.5">
            <Crosshair size={22} />
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-indigo-900 bg-indigo-200/80 px-2 py-0.5 rounded">
                Simulated Adversary · Abstract Parameters Only
              </span>
              <span className="text-xs text-indigo-800 font-medium">Evolutionary Stress-Testing & Policy Tuning</span>
            </div>
            <p className="text-sm font-semibold text-indigo-950">
              Genetic algorithm optimizing abstract laundering parameters against policy defenses.
            </p>
            <p className="text-xs text-indigo-900/90 leading-relaxed">
              The attacker genome explores mathematical trade-offs across layering hops, fan-out spray widths, inter-hop
              delays, and clean balance commingling. Defensive policies are tuned strictly on Attack Families A & B, and
              evaluated against held-out Family C to verify resilience against collateral damage on innocent merchants and aggregators.
            </p>
          </div>
        </div>
      </section>

      {/* 2. Experiment Control Bar */}
      <section className="surface p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4 flex-1">
          <label className="text-xs font-semibold text-slate-700 min-w-[120px]">
            Deterministic Seed
            <select
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              disabled={loading}
              className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-900 shadow-sm"
            >
              <option value={42}>Seed 42 (Standard Baseline)</option>
              <option value={101}>Seed 101 (High-Spray Variation)</option>
              <option value={777}>Seed 777 (Deep-Chain Variation)</option>
              <option value={999}>Seed 999 (Rapid-Timing Variation)</option>
            </select>
          </label>

          <label className="text-xs font-semibold text-slate-700 min-w-[120px]">
            Population Size
            <select
              value={population}
              onChange={(e) => setPopulation(Number(e.target.value))}
              disabled={loading}
              className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-900 shadow-sm"
            >
              <option value={20}>20 candidates</option>
              <option value={24}>24 candidates (default)</option>
              <option value={32}>32 candidates</option>
              <option value={40}>40 candidates (thorough)</option>
            </select>
          </label>

          <label className="text-xs font-semibold text-slate-700 min-w-[120px]">
            Generations Count
            <select
              value={generations}
              onChange={(e) => setGenerations(Number(e.target.value))}
              disabled={loading}
              className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-900 shadow-sm"
            >
              <option value={10}>10 generations (fast)</option>
              <option value={15}>15 generations (balanced)</option>
              <option value={20}>20 generations</option>
              <option value={30}>30 generations (deep)</option>
            </select>
          </label>
        </div>

        <button
          type="button"
          onClick={() => runExperiment(seed, population, generations)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Simulating Generations...' : 'Run Evolutionary Search'}
        </button>
      </section>

      {error && (
        <section className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 flex items-start gap-2.5">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-rose-600" />
          <div>
            <div className="font-semibold">Evolutionary search error</div>
            <div className="text-xs mt-0.5 text-rose-700">{error}</div>
          </div>
        </section>
      )}

      {/* 3. Generation Trajectory Chart */}
      <section className="surface p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <TrendingUp size={16} className="text-indigo-600" />
              Evolutionary Trajectory Across Generations
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Attacker Objective: Maximize escaped stolen rupees + innocent bystander rupees held (collateral damage).
            </p>
          </div>
          {data && (
            <div className="flex items-center gap-2 text-xs">
              <span className="font-medium text-slate-600">Initial Best:</span>
              <span className="font-mono font-bold text-slate-800">
                {inr(data.evolution_history[0]?.best_fitness || 0)}
              </span>
              <span className="text-slate-400">→</span>
              <span className="font-medium text-slate-600">Evolved Best:</span>
              <span className="font-mono font-bold text-indigo-700">
                {inr(data.evolution_history[data.evolution_history.length - 1]?.best_fitness || 0)}
              </span>
            </div>
          )}
        </div>

        {loading ? (
          <div className="h-72 flex flex-col items-center justify-center text-slate-400 text-xs">
            <RefreshCw size={24} className="animate-spin mb-2 text-indigo-500" />
            Executing evolutionary search with genetic selection, crossover & mutation...
          </div>
        ) : (
          <div className="h-72 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="gen" tick={{ fontSize: 11 }} />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(val: any) => [`₹${Number(val).toLocaleString('en-IN')}`, '']}
                  contentStyle={{ fontSize: '11px', borderRadius: '6px' }}
                />
                <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} />
                <Line
                  type="monotone"
                  dataKey="Best Fitness"
                  stroke="#4f46e5"
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="Mean Fitness"
                  stroke="#94a3b8"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                />
                <Line
                  type="monotone"
                  dataKey="Escaped (₹)"
                  stroke="#ef4444"
                  strokeWidth={1.5}
                />
                <Line
                  type="monotone"
                  dataKey="Innocent Held (₹)"
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      {/* 4. Best Evolved Genome Card */}
      {data && (
        <section className="surface p-5 space-y-3">
          <div className="border-b border-slate-100 pb-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
              <Award size={16} className="text-amber-500" />
              Optimal Evolved Attacker Genome (Seed {data.seed})
            </div>
            <span className="text-[11px] font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
              Tuned on Families A & B only
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Layers size={12} /> Hops
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900 font-mono">
                {data.evolved_genome.hops} hops
              </div>
              <div className="text-[10px] text-slate-500">Chain depth</div>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Split size={12} /> Spray Width
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900 font-mono">
                {data.evolved_genome.spray_width} branches
              </div>
              <div className="text-[10px] text-slate-500">Fan-out smurfing</div>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Clock size={12} /> Hop Delay
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900 font-mono">
                {data.evolved_genome.delay_between_hops_minutes} min
              </div>
              <div className="text-[10px] text-slate-500">
                {data.evolved_genome.delay_between_hops_minutes < 120 ? 'Triggers <2h rapid flag' : 'Avoids rapid flag'}
              </div>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Shuffle size={12} /> Clean Mix
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900 font-mono">
                {(data.evolved_genome.clean_mix_share * 100).toFixed(1)}%
              </div>
              <div className="text-[10px] text-slate-500">Commingled legitimate funds</div>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <Clock size={12} /> Cash-Out
              </div>
              <div className="mt-1 text-lg font-bold text-slate-900 font-mono">
                {data.evolved_genome.cash_out_timing_hours}h
              </div>
              <div className="text-[10px] text-slate-500">Delay before ATM/crypto</div>
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                <SlidersHorizontal size={12} /> Split Ratios
              </div>
              <div className="mt-1 text-xs font-mono font-bold text-slate-900 truncate">
                {data.evolved_genome.split_sizes.map((s) => `${(s * 100).toFixed(0)}%`).join(' : ')}
              </div>
              <div className="text-[10px] text-slate-500">Branch disbursement</div>
            </div>
          </div>
        </section>
      )}

      {/* 5. Policy Comparison Section (Policy V1 vs Policy V2 vs Defenses Off) */}
      {data && (
        <section className="surface p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Defense Evaluation: Defenses Off vs Policy V1 vs Policy V2
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Compare naive whole-account freezing against Smart-Freeze consensus-core safeguards.
              </p>
            </div>

            {/* Policy Toggle Buttons */}
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                onClick={() => setSelectedPolicyTab('policy_v2')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors ${
                  selectedPolicyTab === 'policy_v2'
                    ? 'bg-indigo-600 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Policy V2 (Smart-Freeze Safeguards)
              </button>
              <button
                type="button"
                onClick={() => setSelectedPolicyTab('policy_v1')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors ${
                  selectedPolicyTab === 'policy_v1'
                    ? 'bg-rose-600 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Policy V1 (Naive Freeze)
              </button>
              <button
                type="button"
                onClick={() => setSelectedPolicyTab('defenses_off')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors ${
                  selectedPolicyTab === 'defenses_off'
                    ? 'bg-slate-700 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Defenses Off (Unprotected)
              </button>
            </div>
          </div>

          {/* Side-by-Side Comparison Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Left: Tuning Performance (Families A & B) */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Tuning Performance (Families A & B)
                </span>
                <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-semibold">
                  10 Simulated Cases
                </span>
              </div>

              {activeTuningSummary && (
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  <div className="p-2.5 rounded bg-slate-50 border border-slate-100">
                    <span className="text-[10px] text-slate-500 block">Escaped Money</span>
                    <span className="text-sm font-bold font-mono text-rose-700 block mt-0.5">
                      {inr(activeTuningSummary.escaped_money_inr)}
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-slate-50 border border-slate-100">
                    <span className="text-[10px] text-slate-500 block">Innocent Money Held</span>
                    <span className={`text-sm font-bold font-mono block mt-0.5 ${
                      activeTuningSummary.innocent_money_held_inr > 0 ? 'text-amber-700' : 'text-emerald-700'
                    }`}>
                      {inr(activeTuningSummary.innocent_money_held_inr)}
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-slate-50 border border-slate-100">
                    <span className="text-[10px] text-slate-500 block">Total Holds Executed</span>
                    <span className="text-sm font-bold font-mono text-slate-800 block mt-0.5">
                      {activeTuningSummary.number_of_holds} holds
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-slate-50 border border-slate-100">
                    <span className="text-[10px] text-slate-500 block">Attacker Total Fitness</span>
                    <span className="text-sm font-bold font-mono text-indigo-700 block mt-0.5">
                      {inr(activeTuningSummary.attacker_fitness_inr)}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Right: Held-Out Family C (Heavy Commingling Stress-Test) */}
            <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50/40 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-indigo-950 uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle2 size={14} className="text-indigo-600" />
                  Held-Out Stress Test (Family C)
                </span>
                <span className="text-[10px] bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-bold">
                  Never seen during tuning
                </span>
              </div>

              <p className="text-[11px] text-indigo-900 leading-normal">
                Scam Family C routes stolen funds through innocent payment aggregators and fast-settling merchants.
              </p>

              {activeHeldOutSummary && (
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  <div className="p-2.5 rounded bg-white border border-indigo-100">
                    <span className="text-[10px] text-slate-500 block">Escaped Money</span>
                    <span className="text-sm font-bold font-mono text-rose-700 block mt-0.5">
                      {inr(activeHeldOutSummary.escaped_money_inr)}
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-white border border-indigo-100">
                    <span className="text-[10px] text-slate-500 block">Innocent Money Held</span>
                    <span className={`text-sm font-bold font-mono block mt-0.5 ${
                      activeHeldOutSummary.innocent_money_held_inr > 50_000 ? 'text-rose-700 font-extrabold' : 'text-emerald-700'
                    }`}>
                      {inr(activeHeldOutSummary.innocent_money_held_inr)}
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-white border border-indigo-100">
                    <span className="text-[10px] text-slate-500 block">Total Holds Executed</span>
                    <span className="text-sm font-bold font-mono text-slate-800 block mt-0.5">
                      {activeHeldOutSummary.number_of_holds} holds
                    </span>
                  </div>

                  <div className="p-2.5 rounded bg-white border border-indigo-100">
                    <span className="text-[10px] text-slate-500 block">Collateral Damage Ratio</span>
                    <span className="text-sm font-bold font-mono text-slate-800 block mt-0.5">
                      {activeHeldOutSummary.collateral_damage_rate_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default AttackLab;
