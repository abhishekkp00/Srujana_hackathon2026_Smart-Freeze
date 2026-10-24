import React, { useEffect, useState } from 'react';
import {
  Fingerprint,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  Sparkles,
  Info,
  Scale,
  Building2,
  Wallet,
  Landmark,
  ArrowRight,
  Lock,
  Key,
  FileCheck2,
  HelpCircle,
  Layers,
} from 'lucide-react';
import {
  getTraceProofScenarios,
  startTraceProof,
  verifyEvidenceEnvelope,
} from '../api/endpoints';
import {
  TraceProofScenario,
  TraceProofResponse,
  TraceProofEdge,
  SignedEvidenceEnvelope,
  EnvelopeVerificationResult,
} from '../types';
import { StatCard } from '../components/common/StatCard';
import { Badge } from '../components/common/Badge';

export const TraceProof: React.FC = () => {
  const [scenarios, setScenarios] = useState<TraceProofScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('SCENARIO_1_COMPLETE');
  const [traceResult, setTraceResult] = useState<TraceProofResponse | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<TraceProofEdge | null>(null);
  const [activeEnvelope, setActiveEnvelope] = useState<SignedEvidenceEnvelope | null>(null);
  const [reverifyResult, setReverifyResult] = useState<EnvelopeVerificationResult | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [isTracing, setIsTracing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios on mount
  useEffect(() => {
    const fetchScenarios = async () => {
      setLoading(true);
      try {
        const scList = await getTraceProofScenarios();
        setScenarios(scList);
        if (scList.length > 0) {
          // Auto-run first scenario
          await runTrace(scList[0].scenario_id, scList[0].case_id);
        }
      } catch (err: any) {
        console.error('Failed to load TraceProof scenarios:', err);
        setError(err?.response?.data?.detail || err?.message || 'Failed to connect to TraceProof service');
      } finally {
        setLoading(false);
      }
    };
    fetchScenarios();

    const handleAuthChange = () => {
      fetchScenarios();
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => window.removeEventListener('auth-changed', handleAuthChange);
  }, []);

  const runTrace = async (scenarioId: string, caseId: string) => {
    setIsTracing(true);
    setError(null);
    setSelectedEdge(null);
    setActiveEnvelope(null);
    setReverifyResult(null);

    try {
      const res = await startTraceProof({
        scenario_id: scenarioId,
        case_id: caseId,
      });
      setTraceResult(res);
      // Select first edge if available
      if (res.edges.length > 0) {
        handleSelectEdge(res.edges[0], res);
      }
    } catch (err: any) {
      console.error('Trace execution failed:', err);
      setError(err?.response?.data?.detail || err?.message || 'Failed to execute trace');
    } finally {
      setIsTracing(false);
    }
  };

  const handleSelectEdge = (edge: TraceProofEdge, traceContext?: TraceProofResponse) => {
    setSelectedEdge(edge);
    setReverifyResult(null);

    const ctx = traceContext || traceResult;
    if (ctx && edge.envelope_id) {
      const found = ctx.envelopes.find(
        (env) => `${env.institution_id}_${env.source_record_id}` === edge.envelope_id
      );
      setActiveEnvelope(found || null);
    } else {
      setActiveEnvelope(null);
    }
  };

  const handleReverifyEnvelope = async () => {
    if (!activeEnvelope) return;
    try {
      const res = await verifyEvidenceEnvelope(activeEnvelope);
      setReverifyResult(res);
    } catch (err: any) {
      console.error('Verification failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full py-20 text-slate-500 space-x-2">
        <Fingerprint className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">Initializing TraceProof Multi-Rail Evidence Coordinator...</span>
      </div>
    );
  }

  const selectedScenario = scenarios.find((s) => s.scenario_id === selectedScenarioId);

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Banner: Core Objective & Architecture */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-lg bg-teal-50 border border-teal-100 text-teal-700">
              <Fingerprint className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-xl font-bold text-slate-900">
                  TraceProof: Multi-Rail Evidence Reconstruction
                </h2>
                <Badge variant="primary" size="sm">
                  Ed25519 Cryptographic Proofs
                </Badge>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Cross-institution transaction flow verification across Bank A, Wallet B (PPI), and Bank C / Settlement Rail.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 flex items-center">
            <Lock className="w-3.5 h-3.5 mr-1" />
            Signed Envelopes Active
          </span>
          <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200 flex items-center">
            <ShieldCheck className="w-3.5 h-3.5 mr-1 text-teal-600" />
            No Silent Link Invention
          </span>
        </div>
      </div>

      {/* Scenario Selector Carousel/Grid */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Demonstrable Evidence Scenarios
          </h3>
          <span className="text-xs text-slate-500 font-medium">
            Simulates independent institution adapters with cryptographic envelopes
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {scenarios.map((sc) => {
            const isSelected = sc.scenario_id === selectedScenarioId;
            return (
              <div
                key={sc.scenario_id}
                onClick={() => {
                  setSelectedScenarioId(sc.scenario_id);
                  runTrace(sc.scenario_id, sc.case_id);
                }}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-teal-50/50 border-teal-500 shadow-sm ring-1 ring-teal-500'
                    : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <Badge
                    variant={
                      sc.expected_status === 'COMPLETE'
                        ? 'success'
                        : sc.expected_status === 'PARTIAL'
                        ? 'warning'
                        : 'danger'
                    }
                    size="sm"
                  >
                    {sc.expected_status}
                  </Badge>
                  <span className="text-[10px] font-mono text-slate-500">{sc.case_id}</span>
                </div>
                <h4 className="text-xs font-bold text-slate-900 leading-snug">{sc.title}</h4>
                <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{sc.description}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Trace Overview Header & Action Bar */}
      {traceResult && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <Badge
                variant={
                  traceResult.status === 'COMPLETE'
                    ? 'success'
                    : traceResult.status === 'PARTIAL'
                    ? 'warning'
                    : 'danger'
                }
                size="md"
              >
                TRACE STATUS: {traceResult.status}
              </Badge>
              <div className="text-xs text-slate-500 font-mono">
                Request ID: <span className="font-bold text-slate-800">{traceResult.request_id}</span>
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={() => {
                  if (selectedScenario) {
                    runTrace(selectedScenario.scenario_id, selectedScenario.case_id);
                  }
                }}
                disabled={isTracing}
                className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold shadow-sm transition-colors disabled:opacity-60"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>{isTracing ? 'Reconstructing Trail...' : 'Re-run Trace'}</span>
              </button>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3 pt-2 border-t border-slate-100">
            <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-xs">
              <span className="text-slate-500 block text-[11px]">Hops Traversed</span>
              <span className="text-base font-bold text-slate-800 font-mono">{traceResult.total_hops_traversed}</span>
            </div>
            <div className="bg-emerald-50/60 p-2.5 rounded-lg border border-emerald-100 text-xs">
              <span className="text-emerald-700 block text-[11px]">Confirmed Links</span>
              <span className="text-base font-bold text-emerald-800 font-mono">{traceResult.confirmed_links_count}</span>
            </div>
            <div className="bg-amber-50/60 p-2.5 rounded-lg border border-amber-100 text-xs">
              <span className="text-amber-700 block text-[11px]">Unresolved Links</span>
              <span className="text-base font-bold text-amber-800 font-mono">{traceResult.unresolved_links_count}</span>
            </div>
            <div className="bg-teal-50/60 p-2.5 rounded-lg border border-teal-100 text-xs">
              <span className="text-teal-700 block text-[11px]">Signed Envelopes</span>
              <span className="text-base font-bold text-teal-800 font-mono">{traceResult.envelopes.length}</span>
            </div>
            <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-xs col-span-2 sm:col-span-4 lg:col-span-1">
              <span className="text-slate-500 block text-[11px]">Origin Rail</span>
              <span className="text-xs font-bold text-slate-800 truncate block">Bank A (Retail Wire)</span>
            </div>
          </div>

          {/* Narrative Summary Callout */}
          <div className={`p-4 rounded-xl border text-xs leading-relaxed ${
            traceResult.status === 'COMPLETE'
              ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900'
              : traceResult.status === 'PARTIAL'
              ? 'bg-amber-50/50 border-amber-200 text-amber-900'
              : 'bg-rose-50/50 border-rose-200 text-rose-900'
          }`}>
            <span className="font-bold mr-1">Reconstruction Summary:</span>
            {traceResult.narrative_summary}
          </div>
        </div>
      )}

      {/* Main Grid: Multi-Rail Pathway (7 cols) + Evidence & Cryptographic Inspector (5 cols) */}
      {traceResult && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Institutional Multi-Rail Pathway (7 cols) */}
          <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-5">
            <div>
              <h3 className="text-base font-bold text-slate-900 flex items-center">
                <Layers className="w-4 h-4 mr-2 text-teal-600" />
                Multi-Rail Institutional Pathway
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Click any transaction link to inspect cryptographic evidence envelope and signature.
              </p>
            </div>

            {/* Institution Column Headers */}
            <div className="grid grid-cols-3 gap-2 text-center text-xs font-bold py-2 bg-slate-50 rounded-lg border border-slate-200">
              <div className="flex items-center justify-center space-x-1 text-slate-700">
                <Building2 className="w-3.5 h-3.5 text-blue-600" />
                <span>1. Bank A (Retail)</span>
              </div>
              <div className="flex items-center justify-center space-x-1 text-slate-700">
                <Wallet className="w-3.5 h-3.5 text-teal-600" />
                <span>2. Wallet B (PPI)</span>
              </div>
              <div className="flex items-center justify-center space-x-1 text-slate-700">
                <Landmark className="w-3.5 h-3.5 text-indigo-600" />
                <span>3. Bank C (Settlement)</span>
              </div>
            </div>

            {/* Chronological Event Cards List */}
            <div className="space-y-3">
              {traceResult.edges.map((edge, idx) => {
                const isSelected = selectedEdge?.id === edge.id;
                const isUnresolved = edge.link_status === 'UNRESOLVED';
                const isContradictory = edge.link_status === 'CONTRADICTORY';

                return (
                  <div
                    key={edge.id}
                    onClick={() => handleSelectEdge(edge)}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-teal-500 ring-2 ring-teal-500/20 bg-teal-50/30'
                        : isUnresolved
                        ? 'border-amber-300 bg-amber-50/40 hover:bg-amber-50/70 border-dashed'
                        : isContradictory
                        ? 'border-rose-300 bg-rose-50/40 hover:bg-rose-50/70'
                        : 'border-slate-200 hover:border-slate-300 bg-white'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-mono font-bold text-slate-500">#{idx + 1}</span>
                        <Badge
                          variant={
                            edge.link_status === 'CONFIRMED'
                              ? 'success'
                              : isUnresolved
                              ? 'warning'
                              : 'danger'
                          }
                          size="sm"
                        >
                          {edge.link_status}
                        </Badge>
                        <span className="text-xs font-semibold text-slate-800">
                          {edge.event_type.replace(/_/g, ' ')}
                        </span>
                      </div>

                      <div className="text-right">
                        <span className="text-xs font-bold text-slate-900 font-mono">
                          ₹{edge.amount_display.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    </div>

                    {/* Nodes flow: Source -> Target */}
                    <div className="flex items-center space-x-2 text-xs font-mono text-slate-600 my-1 bg-slate-50 p-2 rounded-lg border border-slate-100">
                      <span className="truncate max-w-[140px] text-slate-700" title={edge.source}>
                        {edge.source}
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                      <span
                        className={`truncate max-w-[140px] ${isUnresolved ? 'text-amber-700 font-bold' : 'text-slate-700'}`}
                        title={edge.target}
                      >
                        {edge.target}
                      </span>
                    </div>

                    {/* Footer: Reference, Timestamp & Envelope badge */}
                    <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2">
                      <span className="font-mono truncate max-w-[200px]">Ref: {edge.transaction_reference}</span>
                      <div className="flex items-center space-x-2">
                        <span>{edge.timestamp.slice(11, 19)} UTC</span>
                        {edge.envelope_id ? (
                          <span className="flex items-center text-emerald-700 font-medium">
                            <Lock className="w-3 h-3 mr-0.5" />
                            Signed
                          </span>
                        ) : (
                          <span className="flex items-center text-amber-700 font-medium">
                            <HelpCircle className="w-3 h-3 mr-0.5" />
                            Unverified
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Explicit Unresolved Warning if applicable */}
                    {edge.unresolved_reason && (
                      <div className="mt-2.5 p-2.5 rounded-lg bg-amber-100/70 border border-amber-200 text-amber-900 text-[11px] flex items-start space-x-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-700 flex-shrink-0 mt-0.5" />
                        <span>
                          <strong>Unresolved Link Audit:</strong> {edge.unresolved_reason}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Cryptographic Evidence Inspector & Range Panel (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            {/* Evidence Envelope Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center">
                    <Lock className="w-4 h-4 mr-2 text-teal-600" />
                    Evidence Envelope Inspector
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Ed25519 digital signature & SHA-256 payload audit
                  </p>
                </div>
                {activeEnvelope && (
                  <Badge variant="primary" size="sm">
                    {activeEnvelope.schema_version}
                  </Badge>
                )}
              </div>

              {activeEnvelope ? (
                <div className="space-y-3 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Signing Institution:</span>
                    <span className="font-bold text-slate-800">{activeEnvelope.institution_id}</span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Source Record ID:</span>
                    <span className="font-mono text-slate-800 font-semibold">{activeEnvelope.source_record_id}</span>
                  </div>

                  <div className="flex justify-between py-1.5 border-b border-slate-100">
                    <span className="text-slate-500">Public Key ID:</span>
                    <span className="font-mono text-slate-800">{activeEnvelope.key_id}</span>
                  </div>

                  <div className="space-y-1 py-1.5 border-b border-slate-100">
                    <span className="text-slate-500 block">Payload SHA-256 Digest:</span>
                    <span className="font-mono text-[11px] text-slate-700 bg-slate-50 p-1.5 rounded block break-all border border-slate-200">
                      {activeEnvelope.payload_sha256}
                    </span>
                  </div>

                  <div className="space-y-1 py-1.5 border-b border-slate-100">
                    <span className="text-slate-500 block">Ed25519 Signature (64-byte hex):</span>
                    <span className="font-mono text-[11px] text-teal-800 bg-teal-50/50 p-1.5 rounded block break-all border border-teal-100">
                      {activeEnvelope.signature_hex}
                    </span>
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      onClick={handleReverifyEnvelope}
                      className="px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold text-xs flex items-center space-x-1.5 transition-colors"
                    >
                      <FileCheck2 className="w-3.5 h-3.5 text-teal-600" />
                      <span>Verify Cryptographic Signature</span>
                    </button>

                    {reverifyResult && (
                      <Badge variant={reverifyResult.is_valid ? 'success' : 'danger'} size="sm">
                        {reverifyResult.status}
                      </Badge>
                    )}
                  </div>

                  {reverifyResult && (
                    <div className={`p-3 rounded-lg text-[11px] border ${
                      reverifyResult.is_valid ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'
                    }`}>
                      {reverifyResult.message}
                    </div>
                  )}
                </div>
              ) : selectedEdge?.link_status === 'UNRESOLVED' ? (
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs space-y-2">
                  <div className="flex items-center space-x-2 font-bold">
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                    <span>No Evidence Envelope Exists</span>
                  </div>
                  <p>
                    This transaction link is <strong>unresolved</strong>. The counterparty institution (Bank C) did not supply a signed evidence envelope or the query timed out.
                  </p>
                  <p className="text-[11px] text-amber-700">
                    In compliance with FairHold financial integrity principles, this link remains visibly unverified. It cannot be used to justify lien holds on downstream merchant accounts.
                  </p>
                </div>
              ) : (
                <div className="py-8 text-center text-xs text-slate-400">
                  Select a transaction link to view its cryptographic evidence envelope.
                </div>
              )}
            </div>

            {/* Evidence-Bounded Trace Range Panel */}
            {traceResult.evidence_bounded_range && (
              <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center">
                    <Scale className="w-4 h-4 mr-2 text-teal-600" />
                    Evidence-Bounded Trace Range
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Multi-method fund tracing bounds calculated across verified links.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center p-3 bg-slate-50 rounded-xl border border-slate-100">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Lower Bound</span>
                    <span className="text-base font-extrabold text-slate-900 block font-mono">
                      ₹{traceResult.evidence_bounded_range.lower_bound_display.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Upper Bound</span>
                    <span className="text-base font-extrabold text-slate-900 block font-mono">
                      ₹{traceResult.evidence_bounded_range.upper_bound_display.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Disagreement</span>
                    <span className="text-base font-extrabold text-amber-700 block font-mono">
                      ₹{traceResult.evidence_bounded_range.disagreement_display.toLocaleString('en-IN')}
                    </span>
                  </div>
                </div>

                <div className="space-y-2 pt-1 text-xs">
                  {traceResult.evidence_bounded_range.methods.map((m) => (
                    <div key={m.method} className="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-100">
                      <div>
                        <span className="font-bold text-slate-800">{m.method}</span>
                        <span className="text-[10px] text-slate-500 block">{m.assumption}</span>
                      </div>
                      <span className="font-mono font-bold text-slate-900">
                        ₹{m.amount_display.toLocaleString('en-IN')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Mandatory Governance Notice */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 text-slate-600 space-y-2 text-xs">
        <h4 className="font-bold text-slate-800 flex items-center">
          <ShieldCheck className="w-4 h-4 mr-1.5 text-teal-600" />
          TraceProof Governance & Institutional Trust Framework
        </h4>
        <p>
          TraceProof reconstructs multi-rail transaction paths based strictly on signed institution evidence envelopes. 
          Unresolved, missing, or contradictory links are visibly retained and never silently invented.
        </p>
        <p className="text-slate-500">
          <strong>Trust Model Limitation:</strong> A valid Ed25519 signature confirms envelope payload integrity and institution origin under the configured public-key registry. It does not establish factual judicial proof of guilt or liability. Decision support only: automated account freezes, fund releases, or case closures are strictly prohibited.
        </p>
      </div>
    </div>
  );
};
