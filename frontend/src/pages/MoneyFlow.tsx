import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import cytoscape from 'cytoscape';
import { ArrowRight, AlertCircle, RefreshCw, Scale } from 'lucide-react';
import { getCases, getConsensusLien, getGraphData } from '../api/endpoints';
import { CaseSummary, ConsensusLienData, GraphData, GraphEdge, GraphNode } from '../types';

const inr = (amount: number) => `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const dateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC';
};
const titleCase = (value: string) => value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const edgeLabel = (edge: GraphEdge) =>
  edge.is_source_transaction ? 'SOURCE' :
  edge.linkage_basis === 'CASE_REFERENCE' ? 'CASE LINKED' :
  edge.linkage_basis === 'CHRONOLOGICALLY_REACHABLE' ? 'REACHABLE' :
  edge.linkage_basis === 'ACCOUNT_CONTEXT' ? 'ACCOUNT CONTEXT' : 'LEDGER';

export const MoneyFlow: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedCaseId = searchParams.get('case') || '';
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [lien, setLien] = useState<ConsensusLienData | null>(null);
  const [selectedTx, setSelectedTx] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const graphEl = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCases().then((items) => {
      if (cancelled) return;
      setCases(items);
      const requested = searchParams.get('case') || '';
      const valid = items.some((item) => item.case_id === requested);
      if (!valid && items[0]) setSearchParams({ case: items[0].case_id }, { replace: true });
      if (!items.length) setSearchParams({}, { replace: true });
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load the case list.');
    }).finally(() => { if (!cancelled) setLoadingCases(false); });
    return () => { cancelled = true; };
  }, [refreshKey, setSearchParams]);

  useEffect(() => {
    if (!selectedCaseId || !cases.some((item) => item.case_id === selectedCaseId)) {
      setGraph(null);
      setLien(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getGraphData(selectedCaseId), getConsensusLien(selectedCaseId)])
      .then(([flow, bounds]) => {
        if (cancelled) return;
        setGraph(flow);
        setLien(bounds);
        setSelectedTx(flow.source_transaction_id ?? flow.edges[0]?.id ?? null);
        setSelectedAccount(null);
      })
      .catch((cause: any) => {
        if (!cancelled) {
          setGraph(null);
          setLien(null);
          setError(cause?.response?.data?.detail || cause?.message || 'Could not reconstruct this case.');
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedCaseId, cases, refreshKey]);

  const selectedCase = cases.find((item) => item.case_id === selectedCaseId) ?? null;
  const edges = useMemo(() => (graph?.edges ?? []).slice().sort((a, b) => {
    const diff = Date.parse(a.timestamp) - Date.parse(b.timestamp);
    return diff || a.id.localeCompare(b.id);
  }), [graph]);
  const nodes = graph?.nodes ?? [];
  const currentEdge = edges.find((edge) => edge.id === selectedTx) ?? null;
  const currentNode = nodes.find((node) => node.id === selectedAccount) ?? null;
  const maxHop = edges.reduce((max, edge) => Math.max(max, edge.flow_hop ?? 0), 0);
  const changeCase = (caseId: string) => setSearchParams(caseId ? { case: caseId } : {});

  useEffect(() => {
    const container = graphEl.current;
    if (!container || !graph || !graph.nodes.length) return;
    cyRef.current?.destroy();

    const levelGroups = new Map<number, GraphNode[]>();
    graph.nodes.forEach((node) => {
      const level = node.flow_level ?? 0;
      levelGroups.set(level, [...(levelGroups.get(level) ?? []), node]);
    });
    const positions: Record<string, { x: number; y: number }> = {};
    [...levelGroups.keys()].sort((a, b) => a - b).forEach((level) => {
      const levelNodes = (levelGroups.get(level) ?? []).slice().sort((a, b) => a.id.localeCompare(b.id));
      levelNodes.forEach((node, index) => {
        positions[node.id] = { x: 100 + level * 205, y: 58 + index * 100 };
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
        },
        position: positions[node.id],
      })),
      ...graph.edges.map((edge) => ({
        group: 'edges' as const,
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          amountLabel: inr(edge.amount_inr),
          linkageBasis: edge.linkage_basis ?? 'LEDGER_RECORD',
          isSource: Boolean(edge.is_source_transaction),
          transactionId: edge.id,
        },
      })),
    ];

    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.15,
      maxZoom: 2.2,
      wheelSensitivity: 0.18,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            shape: 'round-rectangle',
            width: '158px',
            height: '48px',
            'background-color': '#F8FAFC',
            'border-width': 1.5,
            'border-color': '#94A3B8',
            color: '#1F2937',
            'font-size': '9px',
            'font-weight': 600,
            'text-wrap': 'wrap',
            'text-max-width': '144px',
            'text-valign': 'center',
            'text-halign': 'center',
            padding: '4px',
          },
        },
        { selector: 'node[?isOrigin]', style: { 'background-color': '#e7ebe5', 'border-color': '#42594a', 'border-width': 2.5, color: '#263b2e' } },
        { selector: 'node[?isExternal]', style: { 'background-color': '#f0f2ed', 'border-color': '#90988f', color: '#454d46' } },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#9CA3AF',
            'target-arrow-color': '#9CA3AF',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.2,
            'curve-style': 'bezier',
            label: 'data(amountLabel)',
            'font-size': '9px',
            color: '#334155',
            'text-background-color': '#FFFFFF',
            'text-background-opacity': 1,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate',
            'line-cap': 'round',
          },
        },
        { selector: 'edge[linkageBasis = "CASE_REFERENCE"]', style: { 'line-color': '#39443c', 'target-arrow-color': '#39443c', width: 2.8 } },
        { selector: 'edge[linkageBasis = "CHRONOLOGICALLY_REACHABLE"]', style: { 'line-color': '#68756b', 'target-arrow-color': '#68756b', 'line-style': 'dashed', width: 2.5 } },
        { selector: 'edge[linkageBasis = "ACCOUNT_CONTEXT"]', style: { 'line-color': '#a0a79f', 'target-arrow-color': '#a0a79f', 'line-style': 'dotted', width: 2 } },
        { selector: 'edge[?isSource]', style: { 'line-color': '#39443c', 'target-arrow-color': '#39443c', width: 3.5 } },
        { selector: ':selected', style: { 'border-width': 3, 'border-color': '#7b806f', 'line-color': '#7b806f', 'target-arrow-color': '#7b806f' } },
      ],
      layout: { name: 'preset', positions: (id) => positions[id], fit: true, padding: 45 },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    cy.on('tap', 'edge', (event) => { setSelectedTx(String(event.target.data('transactionId'))); setSelectedAccount(null); });
    cy.on('tap', 'node', (event) => { setSelectedAccount(String(event.target.id())); setSelectedTx(null); });
    cyRef.current = cy;
    return () => { cy.destroy(); if (cyRef.current === cy) cyRef.current = null; };
  }, [graph]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().unselect();
    if (selectedTx) cy.getElementById(selectedTx).select();
    if (selectedAccount) cy.getElementById(selectedAccount).select();
  }, [selectedTx, selectedAccount]);

  const fitGraph = () => { cyRef.current?.fit(undefined, 40); cyRef.current?.center(); };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <section className="surface flex flex-wrap items-end justify-between gap-3 p-4">
        <label className="min-w-[260px] flex-1 text-xs font-semibold text-slate-600">
          Case
          <select value={selectedCaseId} onChange={(event) => changeCase(event.target.value)} disabled={loadingCases || cases.length === 0} className="mt-1.5 w-full max-w-lg rounded-md border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900">
            {cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {inr(item.reported_amount_inr)}</option>)}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => navigate(`/consensus-lien?case=${encodeURIComponent(selectedCaseId)}`)} disabled={!selectedCaseId} className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"><Scale size={14} /> Compare tracing</button>
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading || loadingCases} className="inline-flex items-center gap-2 rounded-md bg-[#174b3b] px-3 py-2.5 text-xs font-semibold text-white hover:bg-[#0f3d2f] disabled:opacity-50"><RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh</button>
        </div>
      </section>

      {error && <div className="surface flex items-start gap-2 p-4 text-sm text-rose-800"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}

      {loading ? (
        <div className="surface p-10 text-sm text-slate-500">Reconstructing ledger flow and tracing the selected source…</div>
      ) : graph && lien && selectedCase ? (
        <>
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="surface p-4"><div className="text-xs text-slate-500">Source transaction</div><div className="mt-1 font-mono text-sm font-semibold text-slate-900">{graph.source_transaction_id ?? 'Unavailable'}</div><div className="mt-1 text-sm font-semibold text-slate-800">{inr(graph.source_amount_inr ?? 0)}</div></div>
            <div className="surface p-4"><div className="text-xs text-slate-500">Transactions in candidate flow</div><div className="mt-1 text-2xl font-semibold text-slate-900">{graph.total_edges}</div><div className="mt-1 text-xs text-slate-500">{graph.total_nodes} accounts · up to {maxHop} hops</div></div>
            <div className="surface p-4"><div className="text-xs text-slate-500">Consensus Lien range</div>{lien.consensus_status === 'COMPARABLE' ? <><div className="mt-1 text-sm font-semibold text-slate-900">{inr(lien.total_lower_bound_inr)} – {inr(lien.total_upper_bound_inr)}</div><div className="mt-1 text-xs text-slate-500">Disagreement {inr(lien.total_disagreement_inr)}</div></> : <div className="mt-1 text-sm font-semibold text-amber-800">Not comparable</div>}</div>
          </section>

          <section className="surface overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div><h2 className="text-sm font-semibold text-slate-900">Where the money moves</h2><p className="mt-1 text-xs text-slate-500">Select an arrow to inspect its ledger record.</p></div>
              <div className="flex flex-wrap items-center gap-3 text-[10px] text-slate-600">
                <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-slate-600" /> Case-linked</span>
                <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Reachable</span>
                <span className="flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dotted border-slate-400" /> Account context</span>
                <button type="button" onClick={fitGraph} className="rounded border border-slate-200 px-2 py-1 hover:bg-slate-50">Fit</button>
              </div>
            </div>
            {graph.nodes.length && graph.edges.length ? <div ref={graphEl} className="h-[410px] w-full bg-[#fbfcfa]" aria-label="Ledger transaction flow graph" /> : <div className="p-8 text-sm text-slate-500">No source-linked flow was returned for this case.</div>}
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-500">Arrow values are full recorded transaction amounts—not the amount attributed to the source funds. This is synthetic ledger data, not a live bank feed.</div>
          </section>

          <section className="surface overflow-hidden">
            <div className="border-b border-slate-200 px-4 py-3"><h2 className="text-sm font-semibold text-slate-900">Transaction trail</h2><p className="mt-1 text-xs text-slate-500">Real ledger rows, ordered by timestamp. Select a row to highlight its arrow.</p></div>
            {edges.length ? <div className="divide-y divide-slate-100">{edges.slice(0, 12).map((edge) => (
              <button key={edge.id} type="button" onClick={() => { setSelectedTx(edge.id); setSelectedAccount(null); }} className={`grid w-full grid-cols-1 gap-2 px-4 py-3 text-left hover:bg-slate-50 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center ${selectedTx === edge.id ? 'bg-slate-100' : ''}`}>
                <span className="min-w-0"><span className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs font-semibold text-slate-900">{edge.id}</span><span className="rounded border border-slate-200 px-1.5 py-0.5 text-[9px] text-slate-600">{edgeLabel(edge)}</span></span><span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-700"><span className="break-all">{edge.source}</span><ArrowRight size={12} /><span className="break-all">{edge.target}</span></span><span className="mt-1 block text-[10px] text-slate-500">{dateTime(edge.timestamp)} · {titleCase(edge.transaction_type)}</span></span>
                <span className="text-left font-mono text-sm font-semibold text-slate-900 sm:text-right">{inr(edge.amount_inr)}</span>
              </button>
            ))}</div> : <div className="p-6 text-sm text-slate-500">No transactions returned.</div>}
          </section>

          <section className="surface p-4">
            <h2 className="text-sm font-semibold text-slate-900">{currentEdge ? 'Selected transaction' : currentNode ? 'Selected account' : 'Details'}</h2>
            {currentEdge ? <div className="mt-3 grid gap-3 text-xs sm:grid-cols-4"><div><div className="text-slate-500">Transaction</div><div className="mt-1 font-mono font-semibold text-slate-900">{currentEdge.id}</div></div><div><div className="text-slate-500">Recorded amount</div><div className="mt-1 font-semibold text-slate-900">{inr(currentEdge.amount_inr)}</div></div><div><div className="text-slate-500">Linkage</div><div className="mt-1 font-semibold text-slate-900">{edgeLabel(currentEdge)}</div></div><div><div className="text-slate-500">Timestamp</div><div className="mt-1 text-slate-800">{dateTime(currentEdge.timestamp)}</div></div></div> : currentNode ? <div className="mt-3 grid gap-3 text-xs sm:grid-cols-3"><div><div className="text-slate-500">Account</div><div className="mt-1 break-all font-mono font-semibold text-slate-900">{currentNode.id}</div></div><div><div className="text-slate-500">History</div><div className="mt-1 text-slate-800">{currentNode.history_complete == null ? 'Unknown' : currentNode.history_complete ? 'Complete' : 'Incomplete'}</div></div><div><div className="text-slate-500">Final balance</div><div className="mt-1 text-slate-800">{currentNode.final_balance_inr == null ? 'Unavailable' : inr(currentNode.final_balance_inr)}</div></div></div> : <p className="mt-2 text-xs text-slate-500">Select an account or transaction in the graph.</p>}
          </section>
        </>
      ) : !loadingCases ? <div className="surface p-8 text-sm text-slate-500">No case is available in this session.</div> : null}
    </div>
  );
};

export default MoneyFlow;
