import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import cytoscape from 'cytoscape';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleDollarSign,
  GitBranch,
  LockKeyhole,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Scale,
} from 'lucide-react';
import {
  createDemoHoldProposal,
  getCases,
  getConsensusLien,
  getDemoHoldProposals,
  getGraphData,
  getHoldPreview,
} from '../api/endpoints';
import {
  CaseSummary,
  ConsensusLienData,
  DemoHoldProposal,
  GraphData,
  GraphEdge,
  GraphNode,
  HoldCandidate,
  HoldPreview,
} from '../types';

const inr = (amount: number) =>
  `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const dateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('en-IN', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC';
};

const titleCase = (value: string) =>
  value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const linkageLabel = (edge: GraphEdge) =>
  edge.is_source_transaction ? 'SOURCE EVENT' :
  edge.linkage_basis === 'CASE_REFERENCE' ? 'CASE LINKED' :
  edge.linkage_basis === 'CHRONOLOGICALLY_REACHABLE' ? 'FOLLOW-ON PATH' :
  edge.linkage_basis === 'ACCOUNT_CONTEXT' ? 'ACCOUNT CONTEXT' : 'LEDGER EVENT';

const phases = [
  { title: 'Trace funds', subtitle: 'Reconstruct movement' },
  { title: 'Flag evidence', subtitle: 'Identify case-linked activity' },
  { title: 'Calculate amount', subtitle: 'Use balance and lower bound' },
  { title: 'Hold proposal', subtitle: 'Create an auditable simulation' },
];

export const MoneyFlow: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const caseId = searchParams.get('case') || '';
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [lien, setLien] = useState<ConsensusLienData | null>(null);
  const [holdPreview, setHoldPreview] = useState<HoldPreview | null>(null);
  const [proposals, setProposals] = useState<DemoHoldProposal[]>([]);
  const [activeProposal, setActiveProposal] = useState<DemoHoldProposal | null>(null);
  const [selectedTx, setSelectedTx] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [holdAccountId, setHoldAccountId] = useState('');
  const [activePhase, setActivePhase] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playingEdgeIndex, setPlayingEdgeIndex] = useState(0);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loading, setLoading] = useState(false);
  const [creatingHold, setCreatingHold] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const graphEl = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCases()
      .then((items) => {
        if (cancelled) return;
        setCases(items);
        const requested = searchParams.get('case') || '';
        if (!items.some((item) => item.case_id === requested)) {
          if (items[0]) setSearchParams({ case: items[0].case_id }, { replace: true });
          else setSearchParams({}, { replace: true });
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load cases.');
      })
      .finally(() => { if (!cancelled) setLoadingCases(false); });
    return () => { cancelled = true; };
  }, [refreshKey, setSearchParams]);

  useEffect(() => {
    if (!caseId || !cases.some((item) => item.case_id === caseId)) {
      setGraph(null);
      setLien(null);
      setHoldPreview(null);
      setProposals([]);
      setActiveProposal(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotice(null);
    setActivePhase(0);
    setIsPlaying(false);

    Promise.all([
      getGraphData(caseId),
      getConsensusLien(caseId),
      getHoldPreview(caseId),
      getDemoHoldProposals(caseId),
    ])
      .then(([flow, bounds, preview, existingProposals]) => {
        if (cancelled) return;
        setGraph(flow);
        setLien(bounds);
        setHoldPreview(preview);
        setProposals(existingProposals);
        setActiveProposal(existingProposals[0] ?? null);
        const eligible = preview.candidates.filter((candidate) => candidate.is_eligible);
        setHoldAccountId((current) =>
          eligible.some((candidate) => candidate.account_id === current)
            ? current
            : (eligible[0]?.account_id ?? '')
        );
        setSelectedTx(flow.source_transaction_id ?? flow.edges[0]?.id ?? null);
        setSelectedAccount(null);
      })
      .catch((cause: any) => {
        if (!cancelled) {
          setGraph(null);
          setLien(null);
          setHoldPreview(null);
          setError(cause?.response?.data?.detail || cause?.message || 'Could not reconstruct this case.');
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [caseId, cases, refreshKey]);


  const selectedCase = cases.find((item) => item.case_id === caseId) ?? null;
  const edges = useMemo(
    () => (graph?.edges ?? []).slice().sort((a, b) => {
      const diff = Date.parse(a.timestamp) - Date.parse(b.timestamp);
      return diff || a.id.localeCompare(b.id);
    }),
    [graph],
  );
  const nodes = graph?.nodes ?? [];
  const suspiciousEdges = edges.filter((edge) => edge.evidence_status.trim().toLowerCase() === 'suspected_fraud');
  const flaggedNodes = nodes.filter((node) => node.flagged_by_case_evidence);
  const currentEdge = edges.find((edge) => edge.id === selectedTx) ?? null;
  const currentNode = nodes.find((node) => node.id === selectedAccount) ?? null;
  const eligibleCandidates = useMemo(
    () => (holdPreview?.candidates ?? []).filter((candidate) => candidate.is_eligible),
    [holdPreview],
  );
  const selectedCandidate: HoldCandidate | null =
    eligibleCandidates.find((candidate) => candidate.account_id === holdAccountId) ?? null;
  const hopCount = edges.reduce((max, edge) => Math.max(max, edge.flow_hop ?? 0), 0);
  const sourceEdge = edges.find((edge) => edge.is_source_transaction) ?? edges[0] ?? null;
  useEffect(() => {
    if (!isPlaying) return;
    const shouldAnimatePath = activePhase === 0 && edges.length > 1 && playingEdgeIndex < edges.length - 1;
    const timer = window.setTimeout(() => {
      if (shouldAnimatePath) {
        setPlayingEdgeIndex((current) => Math.min(current + 1, edges.length - 1));
        return;
      }
      setActivePhase((current) => {
        if (current >= phases.length - 1) {
          setIsPlaying(false);
          return current;
        }
        setPlayingEdgeIndex(0);
        return current + 1;
      });
    }, shouldAnimatePath ? 750 : 1800);
    return () => window.clearTimeout(timer);
  }, [isPlaying, activePhase, playingEdgeIndex, edges.length]);

  const changeCase = (nextCaseId: string) => {
    setIsPlaying(false);
    setSearchParams(nextCaseId ? { case: nextCaseId } : {});
  };
  const selectPhase = (index: number) => {
    setIsPlaying(false);
    setPlayingEdgeIndex(0);
    setActivePhase(index);
  };

  const runHoldSimulation = async () => {
    if (!selectedCandidate || !caseId || creatingHold) return;
    setCreatingHold(true);
    setError(null);
    setNotice(null);
    try {
      const record = await createDemoHoldProposal({ case_id: caseId, account_id: selectedCandidate.account_id });
      setActiveProposal(record);
      setProposals((current) => [record, ...current.filter((item) => item.proposal_id !== record.proposal_id)]);
      setActivePhase(3);
      setIsPlaying(false);
      setNotice('Simulation recorded in the backend audit trail. No bank connection was called and no funds were frozen.');
    } catch (cause: any) {
      setError(cause?.response?.data?.detail || cause?.message || 'Could not create the simulated hold proposal.');
    } finally {
      setCreatingHold(false);
    }
  };

  useEffect(() => {
    const container = graphEl.current;
    if (!container || !graph || graph.nodes.length === 0) return;
    cyRef.current?.destroy();

    const groups = new Map<number, GraphNode[]>();
    for (const node of graph.nodes) {
      const level = node.flow_level ?? 0;
      groups.set(level, [...(groups.get(level) ?? []), node]);
    }
    const positions: Record<string, { x: number; y: number }> = {};
    [...groups.keys()].sort((a, b) => a - b).forEach((level) => {
      const list = (groups.get(level) ?? []).slice().sort((a, b) => a.id.localeCompare(b.id));
      list.forEach((node, index) => {
        positions[node.id] = { x: 100 + level * 205, y: 64 + index * 94 };
      });
    });

    const elements: cytoscape.ElementDefinition[] = [
      ...graph.nodes.map((node) => ({
        group: 'nodes' as const,
        data: {
          id: node.id,
          label: node.id,
          isExternal: node.is_external,
          isOrigin: Boolean(node.is_origin_account),
          flaggedByEvidence: Boolean(node.flagged_by_case_evidence),
        },
        position: positions[node.id],
      })),
      ...graph.edges.map((edge) => ({
        group: 'edges' as const,
        data: {
          id: edge.id,
          transactionId: edge.id,
          source: edge.source,
          target: edge.target,
          amountLabel: inr(edge.amount_inr),
          linkageBasis: edge.linkage_basis ?? 'LEDGER_RECORD',
          evidenceStatus: edge.evidence_status,
          isSource: Boolean(edge.is_source_transaction),
        },
      })),
    ];

    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.15,
      maxZoom: 2.4,
      wheelSensitivity: 0.18,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            shape: 'round-rectangle',
            width: '158px',
            height: '48px',
            'background-color': '#fafbf9',
            'border-width': 1.4,
            'border-color': '#ccd2ca',
            color: '#263029',
            'font-size': '9px',
            'font-weight': 550,
            'text-wrap': 'wrap',
            'text-max-width': '144px',
            'text-valign': 'center',
            'text-halign': 'center',
            padding: '4px',
          },
        },
        { selector: 'node[?isOrigin]', style: { 'background-color': '#edf1eb', 'border-color': '#6d7c6b', 'border-width': 2.2 } },
        { selector: 'node[?isExternal]', style: { 'background-color': '#f1f1ed', 'border-color': '#b9beb6', color: '#515951' } },
        { selector: 'node[?flaggedByEvidence]', style: { 'border-color': '#8f784a', 'border-width': 2.5 } },
        { selector: 'node.phase-focus', style: { 'border-color': '#344e3d', 'border-width': 3.5, 'background-color': '#eef2ec', color: '#1f3325' } },
        { selector: 'node.hold-target', style: { 'border-color': '#263f30', 'border-width': 4, 'background-color': '#e6ece4', color: '#1e3829' } },
        {
          selector: 'edge',
          style: {
            width: 1.8,
            'line-color': '#adb4ac',
            'target-arrow-color': '#adb4ac',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.15,
            'curve-style': 'bezier',
            label: 'data(amountLabel)',
            'font-size': '9px',
            color: '#414a42',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.96,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate',
            'line-cap': 'round',
          },
        },
        { selector: 'edge[linkageBasis = "CASE_REFERENCE"]', style: { 'line-color': '#59675c', 'target-arrow-color': '#59675c', width: 2.4 } },
        { selector: 'edge[linkageBasis = "CHRONOLOGICALLY_REACHABLE"]', style: { 'line-color': '#89938a', 'target-arrow-color': '#89938a', 'line-style': 'dashed', width: 2 } },
        { selector: 'edge[linkageBasis = "ACCOUNT_CONTEXT"]', style: { 'line-color': '#b5bbb3', 'target-arrow-color': '#b5bbb3', 'line-style': 'dotted', width: 1.8 } },
        { selector: 'edge[?isSource]', style: { 'line-color': '#263f30', 'target-arrow-color': '#263f30', width: 3 } },
        { selector: 'edge[ evidenceStatus = "suspected_fraud" ]', style: { 'line-color': '#8f784a', 'target-arrow-color': '#8f784a', width: 2.7 } },
        { selector: 'edge.phase-focus', style: { 'line-color': '#263f30', 'target-arrow-color': '#263f30', width: 4, 'z-index': 99 } },
        { selector: 'edge.phase-secondary', style: { 'line-color': '#8f784a', 'target-arrow-color': '#8f784a', width: 3.3 } },
        { selector: ':selected', style: { 'border-width': 3.5, 'border-color': '#64705f', 'line-color': '#64705f', 'target-arrow-color': '#64705f' } },
      ],
      layout: { name: 'preset', positions: (id) => positions[id], fit: true, padding: 42 },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    cy.on('tap', 'edge', (event) => {
      setSelectedTx(String(event.target.data('transactionId')));
      setSelectedAccount(null);
      setIsPlaying(false);
    });
    cy.on('tap', 'node', (event) => {
      setSelectedAccount(String(event.target.id()));
      setSelectedTx(null);
      setIsPlaying(false);
    });
    cyRef.current = cy;
    return () => { cy.destroy(); if (cyRef.current === cy) cyRef.current = null; };
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !graph) return;
    cy.nodes().removeClass('phase-focus hold-target');
    cy.edges().removeClass('phase-focus phase-secondary');

    if (activePhase === 0 && sourceEdge) {
      const focusedEdge = isPlaying ? (edges[playingEdgeIndex] ?? sourceEdge) : sourceEdge;
      const edge = cy.getElementById(focusedEdge.id);
      edge.addClass('phase-focus');
      edge.connectedNodes().addClass('phase-focus');
    } else if (activePhase === 1) {
      cy.nodes().filter((node) => Boolean(node.data('flaggedByEvidence'))).addClass('phase-focus');
      cy.edges().filter((edge) => String(edge.data('evidenceStatus')).toLowerCase() === 'suspected_fraud').addClass('phase-secondary');
    } else if (activePhase >= 2 && holdAccountId) {
      cy.getElementById(holdAccountId).addClass('hold-target');
      cy.getElementById(holdAccountId).neighborhood('edge').addClass('phase-focus');
    }
  }, [activePhase, graph, holdAccountId, sourceEdge, edges, isPlaying, playingEdgeIndex]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().unselect();
    if (selectedTx) cy.getElementById(selectedTx).select();
    if (selectedAccount) cy.getElementById(selectedAccount).select();
  }, [selectedTx, selectedAccount]);

  const fitGraph = () => { cyRef.current?.fit(undefined, 42); cyRef.current?.center(); };
  const startWalkthrough = () => {
    setActivePhase(0);
    setPlayingEdgeIndex(0);
    setIsPlaying(true);
  };
  const selectedPhaseEdge = activePhase === 0
    ? sourceEdge
    : activePhase === 1
      ? (suspiciousEdges[0] ?? sourceEdge)
      : edges.find((edge) => edge.source === holdAccountId || edge.target === holdAccountId) ?? sourceEdge;

  const currentProposal = activeProposal && activeProposal.case_id === caseId && activeProposal.account_id === holdAccountId
    ? activeProposal
    : proposals.find((item) => item.account_id === holdAccountId) ?? null;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <section className="surface flex flex-wrap items-end justify-between gap-3 p-4">
        <label className="min-w-[260px] flex-1 text-xs font-semibold text-slate-600">
          Investigation case
          <select value={caseId} onChange={(event) => changeCase(event.target.value)} disabled={loadingCases || cases.length === 0} className="mt-1.5 w-full max-w-lg rounded-md border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900">
            {cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {inr(item.reported_amount_inr)}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => navigate(`/consensus-lien?case=${encodeURIComponent(caseId)}`)} disabled={!caseId} className="inline-flex items-center gap-2 border border-slate-300 bg-white px-3 py-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"><Scale size={14} /> Compare methods</button>
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading || loadingCases} className="inline-flex items-center gap-2 border border-slate-700 bg-slate-800 px-3 py-2.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"><RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh data</button>
        </div>
      </section>

      {error && <div className="surface flex items-start gap-2 p-4 text-sm text-slate-800"><AlertTriangle size={16} className="mt-0.5 shrink-0" />{error}</div>}
      {notice && <div className="surface flex items-start gap-2 p-4 text-sm text-slate-700"><Check size={16} className="mt-0.5 shrink-0" />{notice}</div>}

      {loading ? (
        <div className="surface p-10 text-sm text-slate-500">Reading ledger events and calculating tracing results…</div>
      ) : graph && lien && holdPreview && selectedCase ? (
        <>
          <section className="surface overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Investigation walkthrough</h2>
                <p className="mt-1 text-xs text-slate-500">Follow the recorded flow, inspect evidence flags, calculate a conservative hold proposal.</p>
              </div>
              <button type="button" onClick={isPlaying ? () => setIsPlaying(false) : startWalkthrough} className="inline-flex items-center gap-2 border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
                {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                {isPlaying ? 'Pause walkthrough' : activePhase === phases.length - 1 ? 'Replay walkthrough' : 'Play walkthrough'}
              </button>
            </div>

            <div className="grid grid-cols-2 border-b border-slate-200 md:grid-cols-4">
              {phases.map((phase, index) => (
                <button
                  key={phase.title}
                  type="button"
                  onClick={() => selectPhase(index)}
                  className={`relative min-h-[84px] border-b-2 px-3 py-3 text-left transition-colors md:border-b-0 md:border-r md:last:border-r-0 ${activePhase === index ? 'border-b-slate-800 bg-slate-50 md:bg-slate-50' : 'border-b-transparent hover:bg-slate-50'}`}
                >
                  <span className="flex items-center gap-2">
                    <span className={`flex h-6 w-6 items-center justify-center rounded-sm border text-xs ${activePhase === index ? 'border-slate-700 bg-slate-800 text-white' : 'border-slate-300 text-slate-600'}`}>{index + 1}</span>
                    <span className="text-sm font-semibold text-slate-900">{phase.title}</span>
                  </span>
                  <span className="mt-2 block pl-8 text-[11px] text-slate-500">{phase.subtitle}</span>
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-0 xl:grid-cols-[minmax(0,1.7fr)_minmax(290px,0.8fr)]">
              <div className="min-w-0 border-b border-slate-200 xl:border-b-0 xl:border-r">
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">Transaction path</h3>
                    <p className="mt-1 text-[11px] text-slate-500">Select any account or arrow. The selected phase highlights its relevant evidence.</p>
                  </div>
                  <button type="button" onClick={fitGraph} className="border border-slate-300 px-2.5 py-1.5 text-[11px] text-slate-600 hover:bg-slate-50">Fit graph</button>
                </div>
                {graph.nodes.length && graph.edges.length
                  ? <div ref={graphEl} className="h-[390px] w-full bg-white" aria-label="Animated transaction tracing graph" />
                  : <div className="p-8 text-sm text-slate-500">No ledger path was returned for this case.</div>}
                <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-slate-200 bg-slate-50 px-4 py-2 text-[10px] text-slate-600">
                  <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-slate-700" /> Case-linked transfer</span>
                  <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Reachable path</span>
                  <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dotted border-slate-400" /> Account context</span>
                  <span className="flex items-center gap-1.5"><span className="h-3 w-3 border-2 border-[#8f784a]" /> Evidence-flagged account</span>
                </div>
              </div>

              <div className="min-w-0 p-4">
                {activePhase === 0 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-slate-800"><GitBranch size={17} /><h3 className="text-sm font-semibold">1. Trace the source</h3></div>
                    <div className="border-b border-slate-200 pb-3">
                      <div className="text-[11px] text-slate-500">Source transaction</div>
                      <div className="mt-1 font-mono text-sm font-semibold text-slate-900">{graph.source_transaction_id ?? 'Unavailable'}</div>
                      <div className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{inr(graph.source_amount_inr ?? 0)}</div>
                      {sourceEdge && <div className="mt-2 text-xs leading-5 text-slate-600">{sourceEdge.source} <ArrowRight className="mx-1 inline" size={12} /> {sourceEdge.target}<br />{dateTime(sourceEdge.timestamp)}</div>}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><div className="text-[11px] text-slate-500">Recorded events</div><div className="mt-1 text-lg font-semibold text-slate-900">{graph.total_edges}</div></div>
                      <div><div className="text-[11px] text-slate-500">Accounts / hops</div><div className="mt-1 text-lg font-semibold text-slate-900">{graph.total_nodes} / {hopCount}</div></div>
                    </div>
                    <p className="text-xs leading-5 text-slate-600">The graph is built from the selected case’s source transaction and later time-ordered ledger events. Arrow labels show the recorded transfer amount, not proven source-lot content.</p>
                    <button type="button" onClick={() => selectPhase(1)} className="inline-flex items-center gap-2 border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50">Inspect suspicious activity <ArrowRight size={13} /></button>
                  </div>
                )}

                {activePhase === 1 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-slate-800"><AlertTriangle size={17} /><h3 className="text-sm font-semibold">2. Flag case evidence</h3></div>
                    <div className="grid grid-cols-2 gap-3 border-b border-slate-200 pb-3">
                      <div><div className="text-[11px] text-slate-500">Flagged transaction rows</div><div className="mt-1 text-2xl font-semibold text-slate-900">{suspiciousEdges.length}</div></div>
                      <div><div className="text-[11px] text-slate-500">Accounts touched</div><div className="mt-1 text-2xl font-semibold text-slate-900">{flaggedNodes.length}</div></div>
                    </div>
                    <div className="space-y-0">
                      {suspiciousEdges.slice(0, 4).map((edge) => (
                        <button key={edge.id} type="button" onClick={() => { setSelectedTx(edge.id); setSelectedAccount(null); }} className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-2 border-b border-slate-100 py-2 text-left hover:bg-slate-50 ${selectedTx === edge.id ? 'bg-slate-100' : ''}`}>
                          <span className="min-w-0"><span className="block font-mono text-xs font-semibold text-slate-900">{edge.id}</span><span className="mt-1 block truncate text-[11px] text-slate-600">{edge.source} → {edge.target}</span></span>
                          <span className="self-center font-mono text-xs text-slate-900">{inr(edge.amount_inr)}</span>
                        </button>
                      ))}
                      {suspiciousEdges.length === 0 && <div className="py-3 text-xs text-slate-500">No transaction row in the selected graph carries a suspected-fraud evidence flag.</div>}
                    </div>
                    <p className="text-xs leading-5 text-slate-600">The flag comes from the ledger’s evidence_status field. It is an investigative signal, not a finding that an account holder committed fraud.</p>
                    <button type="button" onClick={() => selectPhase(2)} className="inline-flex items-center gap-2 border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50">Calculate hold amount <ArrowRight size={13} /></button>
                  </div>
                )}

                {activePhase === 2 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-slate-800"><CircleDollarSign size={17} /><h3 className="text-sm font-semibold">3. Calculate a proposed amount</h3></div>
                    <label className="block text-xs font-medium text-slate-600">Candidate account
                      <select value={holdAccountId} onChange={(event) => { setHoldAccountId(event.target.value); setActiveProposal(null); }} className="mt-1.5 w-full border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900" disabled={!eligibleCandidates.length}>
                        {eligibleCandidates.map((candidate) => <option value={candidate.account_id} key={candidate.account_id}>{candidate.account_id}</option>)}
                      </select>
                    </label>
                    {selectedCandidate ? (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="border border-slate-200 p-3"><div className="text-[11px] text-slate-500">Current ledger balance</div><div className="mt-1 text-lg font-semibold text-slate-900">{inr(selectedCandidate.current_balance_inr ?? 0)}</div></div>
                          <div className="border border-slate-200 p-3"><div className="text-[11px] text-slate-500">Consensus lower bound</div><div className="mt-1 text-lg font-semibold text-slate-900">{inr(selectedCandidate.lower_bound_inr)}</div></div>
                        </div>
                        <div className="border-t border-slate-200 pt-3">
                          <div className="text-[11px] text-slate-500">Proposed hold cap</div>
                          <div className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{inr(selectedCandidate.proposed_hold_inr)}</div>
                          <div className="mt-2 text-[11px] leading-5 text-slate-600">min({inr(selectedCandidate.lower_bound_inr)} lower bound, {inr(selectedCandidate.current_balance_inr ?? 0)} reconstructed balance)</div>
                        </div>
                        <div className="text-xs leading-5 text-slate-600">This cap is recalculated by the FastAPI service from the selected account’s tracing result and ledger balance. It is not a legal determination.</div>
                      </>
                    ) : (
                      <div className="border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
                        No account currently meets the demo eligibility checks. The service requires a positive conservative bound, a positive observed balance, and complete statement history.
                      </div>
                    )}
                    <button type="button" onClick={() => selectPhase(3)} className="inline-flex items-center gap-2 border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50">Review hold request <ArrowRight size={13} /></button>
                  </div>
                )}

                {activePhase === 3 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-slate-800"><LockKeyhole size={17} /><h3 className="text-sm font-semibold">4. Simulate a hold request</h3></div>
                    <div className="border border-slate-300 bg-slate-50 p-3">
                      <div className="text-[11px] text-slate-500">Account selected for proposal</div>
                      <div className="mt-1 font-mono text-sm font-semibold text-slate-900">{selectedCandidate?.account_id ?? 'No eligible account'}</div>
                      <div className="mt-2 text-2xl font-semibold text-slate-900">{selectedCandidate ? inr(selectedCandidate.proposed_hold_inr) : 'Unavailable'}</div>
                      <div className="mt-1 text-[11px] text-slate-500">Proposed amount · not frozen funds</div>
                    </div>

                    {currentProposal ? (
                      <div className="space-y-3 border-t border-slate-200 pt-3">
                        <div className="text-sm font-semibold text-slate-900">Simulation record created</div>
                        <div className="grid grid-cols-2 gap-3 text-xs">
                          <div><div className="text-slate-500">Proposal ID</div><div className="mt-1 break-all font-mono text-slate-900">{currentProposal.proposal_id}</div></div>
                          <div><div className="text-slate-500">Audit event</div><div className="mt-1 break-all font-mono text-slate-900">{currentProposal.audit_event_id}</div></div>
                          <div><div className="text-slate-500">Recorded at</div><div className="mt-1 text-slate-800">{dateTime(currentProposal.created_at)}</div></div>
                          <div><div className="text-slate-500">Status</div><div className="mt-1 text-slate-800">Pending review · simulation only</div></div>
                        </div>
                        <button type="button" onClick={() => setActiveProposal(null)} className="border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">Create another proposal</button>
                      </div>
                    ) : (
                      <button type="button" onClick={() => void runHoldSimulation()} disabled={!selectedCandidate || creatingHold} className="inline-flex w-full items-center justify-center gap-2 border border-slate-800 bg-slate-800 px-3 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
                        {creatingHold ? <RefreshCw size={14} className="animate-spin" /> : <LockKeyhole size={14} />}
                        {creatingHold ? 'Recording proposal…' : 'Create simulated hold request'}
                      </button>
                    )}

                    <div className="border-t border-slate-200 pt-3 text-xs leading-5 text-slate-600">
                      <div className="font-semibold text-slate-800">What the request uses</div>
                      <ul className="mt-2 space-y-1.5">
                        <li>• Selected case and source transaction: {graph.source_transaction_id ?? 'unavailable'}</li>
                        <li>• Account-level Consensus Lien lower bound</li>
                        <li>• Reconstructed closing balance and complete-history check</li>
                        <li>• Audit event with proposal ID, case, account and amount</li>
                      </ul>
                      <p className="mt-3 font-medium text-slate-800">This is a local simulation. No bank API is called and no real account is frozen.</p>
                    </div>
                    <p className="text-[11px] leading-5 text-slate-500">{holdPreview.disclaimer} Proposal and audit records exist in backend memory for this demo process only.</p>
                    {currentProposal && (
                      <button type="button" onClick={() => navigate(`/consensus-lien?case=${encodeURIComponent(caseId)}`)} className="inline-flex items-center gap-2 border border-slate-300 px-3 py-2 text-xs font-medium hover:bg-slate-50"><Scale size={13} /> View tracing calculations</button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="surface overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div><h2 className="text-sm font-semibold text-slate-900">Selected ledger record</h2><p className="mt-1 text-xs text-slate-500">Select a graph arrow or account to inspect its source record.</p></div>
              <span className="text-[11px] text-slate-500">{graph.total_edges} events · {graph.total_nodes} nodes</span>
            </div>
            {currentEdge ? (
              <div className="grid gap-3 p-4 text-xs sm:grid-cols-4">
                <div><div className="text-slate-500">Transaction</div><div className="mt-1 font-mono font-semibold text-slate-900">{currentEdge.id}</div></div>
                <div><div className="text-slate-500">Recorded amount</div><div className="mt-1 font-semibold text-slate-900">{inr(currentEdge.amount_inr)}</div></div>
                <div><div className="text-slate-500">Evidence status</div><div className="mt-1 font-medium text-slate-900">{titleCase(currentEdge.evidence_status)}</div><div className="mt-1 text-slate-500">{linkageLabel(currentEdge)}</div></div>
                <div><div className="text-slate-500">Timestamp</div><div className="mt-1 text-slate-800">{dateTime(currentEdge.timestamp)}</div></div>
              </div>
            ) : currentNode ? (
              <div className="grid gap-3 p-4 text-xs sm:grid-cols-4">
                <div><div className="text-slate-500">Account</div><div className="mt-1 break-all font-mono font-semibold text-slate-900">{currentNode.id}</div></div>
                <div><div className="text-slate-500">Evidence flag</div><div className="mt-1 text-slate-800">{currentNode.flagged_by_case_evidence ? 'Linked to suspected transaction' : 'No selected-case flag'}</div></div>
                <div><div className="text-slate-500">Statement history</div><div className="mt-1 text-slate-800">{currentNode.history_complete == null ? 'Not available in this scope' : currentNode.history_complete ? 'Complete' : 'Incomplete'}</div></div>
                <div><div className="text-slate-500">Closing balance</div><div className="mt-1 text-slate-800">{currentNode.final_balance_inr == null ? 'Unavailable in graph response' : inr(currentNode.final_balance_inr)}</div></div>
              </div>
            ) : (
              <div className="p-4 text-xs text-slate-500">Choose a transaction or account in the graph to see its details.</div>
            )}
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">{graph.flow_scope}</div>
          </section>
        </>
      ) : !loadingCases ? (
        <section className="surface p-8 text-sm text-slate-500">No case is available for this session.</section>
      ) : null}
    </div>
  );
};

export default MoneyFlow;
