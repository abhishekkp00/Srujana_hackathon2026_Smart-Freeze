import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import cytoscape from 'cytoscape';
import {
  ArrowDownRight,
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  GitBranch,
  RefreshCw,
  ShieldAlert,
  Waypoints,
} from 'lucide-react';
import { getCases, getConsensusLien, getGraphData } from '../api/endpoints';
import { CaseSummary, ConsensusLienData, GraphData, GraphEdge, GraphNode } from '../types';
import { Badge } from '../components/common/Badge';

const formatINR = (value: number) =>
  `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const formatTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('en-IN', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC';
};

const formatLabel = (value: string) =>
  value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const basisLabel = (edge: GraphEdge) =>
  edge.is_source_transaction
    ? 'Source transaction'
    : edge.linkage_basis === 'CASE_REFERENCE'
      ? 'Linked to this case'
      : edge.linkage_basis === 'CHRONOLOGICALLY_REACHABLE'
        ? 'Chronologically reachable'
        : 'Ledger transaction';

const basisVariant = (edge: GraphEdge): 'danger' | 'warning' | 'neutral' =>
  edge.is_source_transaction || edge.linkage_basis === 'CASE_REFERENCE'
    ? 'danger'
    : edge.linkage_basis === 'CHRONOLOGICALLY_REACHABLE'
      ? 'warning'
      : 'neutral';

export const MoneyFlow: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState(searchParams.get('case') || '');
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [consensus, setConsensus] = useState<ConsensusLienData | null>(null);
  const [selectedTransactionId, setSelectedTransactionId] = useState<string | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [loadingFlow, setLoadingFlow] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const cyContainerRef = useRef<HTMLDivElement>(null);
  const cyInstanceRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadCases = async () => {
      setLoadingCases(true);
      try {
        const response = await getCases();
        if (cancelled) return;
        setCases(response);
        setSelectedCaseId((current) =>
          current && response.some((item) => item.case_id === current)
            ? current
            : (response[0]?.case_id ?? '')
        );
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load cases from the API.');
      } finally {
        if (!cancelled) setLoadingCases(false);
      }
    };
    void loadCases();
    return () => { cancelled = true; };
  }, [refreshKey]);

  useEffect(() => {
    if (!selectedCaseId) {
      setGraphData(null);
      setConsensus(null);
      setSelectedTransactionId(null);
      setLoadingFlow(false);
      return;
    }
    let cancelled = false;
    setLoadingFlow(true);
    setError(null);
    setGraphData(null);
    setConsensus(null);
    setSelectedTransactionId(null);
    setSelectedAccountId(null);

    Promise.all([getGraphData(selectedCaseId), getConsensusLien(selectedCaseId)])
      .then(([graph, lien]) => {
        if (cancelled) return;
        setGraphData(graph);
        setConsensus(lien);
        setSelectedTransactionId(graph.source_transaction_id ?? graph.edges.find((edge) => edge.is_source_transaction)?.id ?? null);
      })
      .catch((cause: any) => {
        if (cancelled) return;
        setError(cause?.response?.data?.detail || cause?.message || 'The API could not reconstruct this case flow.');
      })
      .finally(() => { if (!cancelled) setLoadingFlow(false); });

    return () => { cancelled = true; };
  }, [selectedCaseId, refreshKey]);

  const selectedCase = useMemo(
    () => cases.find((item) => item.case_id === selectedCaseId) ?? null,
    [cases, selectedCaseId],
  );

  const edges = useMemo(
    () => (graphData?.edges ?? []).slice().sort((a, b) => {
      const byTime = Date.parse(a.timestamp) - Date.parse(b.timestamp);
      return Number.isNaN(byTime) || byTime === 0 ? a.id.localeCompare(b.id) : byTime;
    }),
    [graphData],
  );

  const selectedEdge = useMemo(
    () => edges.find((edge) => edge.id === selectedTransactionId) ?? null,
    [edges, selectedTransactionId],
  );
  const selectedNode = useMemo(
    () => graphData?.nodes.find((node) => node.id === selectedAccountId) ?? null,
    [graphData, selectedAccountId],
  );
  const lienByAccount = useMemo(
    () => new Map((consensus?.account_liens ?? []).map((item) => [item.account_id, item])),
    [consensus],
  );
  const sourceEdge = edges.find((edge) => edge.is_source_transaction) ?? edges[0] ?? null;
  const referenceCount = edges.filter((edge) => edge.linkage_basis === 'CASE_REFERENCE' || edge.is_source_transaction).length;
  const temporalCount = edges.filter((edge) => edge.linkage_basis === 'CHRONOLOGICALLY_REACHABLE').length;
  const hopCount = edges.reduce((max, edge) => Math.max(max, edge.flow_hop ?? 0), 0);

  useEffect(() => {
    const container = cyContainerRef.current;
    if (!container || !graphData || graphData.nodes.length === 0) return;

    cyInstanceRef.current?.destroy();
    const levels = new Map<number, GraphNode[]>();
    for (const node of graphData.nodes) {
      const level = node.flow_level ?? 0;
      levels.set(level, [...(levels.get(level) ?? []), node]);
    }
    const positions: Record<string, { x: number; y: number }> = {};
    const levelKeys = [...levels.keys()].sort((a, b) => a - b);
    for (const level of levelKeys) {
      const nodes = (levels.get(level) ?? []).slice().sort((a, b) => a.id.localeCompare(b.id));
      nodes.forEach((node, index) => {
        positions[node.id] = {
          x: 95 + level * 220,
          y: 65 + index * 98,
        };
      });
    }

    const elements: cytoscape.ElementDefinition[] = [
      ...graphData.nodes.map((node) => ({
        group: 'nodes' as const,
        data: {
          id: node.id,
          label: node.id,
          accountType: node.type,
          isExternal: node.is_external,
          isOrigin: Boolean(node.is_origin_account),
          historyComplete: node.history_complete,
          flowLevel: node.flow_level ?? 0,
        },
        position: positions[node.id],
      })),
      ...graphData.edges.map((edge) => ({
        group: 'edges' as const,
        data: {
          id: edge.id,
          transactionId: edge.id,
          source: edge.source,
          target: edge.target,
          amountInr: edge.amount_inr,
          amountLabel: `₹${Math.round(edge.amount_inr).toLocaleString('en-IN')}`,
          timestamp: edge.timestamp,
          evidenceStatus: edge.evidence_status,
          linkageBasis: edge.linkage_basis ?? 'LEDGER_RECORD',
          isSourceTransaction: Boolean(edge.is_source_transaction),
          flowHop: edge.flow_hop ?? 0,
        },
      })),
    ];

    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.12,
      maxZoom: 2.5,
      wheelSensitivity: 0.18,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            shape: 'round-rectangle',
            width: 150,
            height: 48,
            'background-color': '#F8FAFC',
            'border-width': 1.5,
            'border-color': '#94A3B8',
            color: '#1F2937',
            'font-size': 9,
            'font-weight': 600,
            'text-wrap': 'wrap',
            'text-max-width': 136,
            'text-valign': 'center',
            'text-halign': 'center',
            'text-background-opacity': 0,
            padding: 4,
          },
        },
        {
          selector: 'node[?isOrigin]',
          style: {
            'background-color': '#D1FAE5',
            'border-color': '#047857',
            'border-width': 3,
            color: '#064E3B',
          },
        },
        {
          selector: 'node[?isExternal]',
          style: {
            shape: 'round-rectangle',
            'background-color': '#FFF7ED',
            'border-color': '#C2410C',
            color: '#7C2D12',
          },
        },
        {
          selector: 'node[?historyComplete = false]',
          style: { 'border-style': 'dashed', 'border-color': '#DC2626', 'border-width': 2.5 },
        },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#94A3B8',
            'target-arrow-color': '#94A3B8',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.15,
            'curve-style': 'bezier',
            label: 'data(amountLabel)',
            'font-size': 9,
            color: '#334155',
            'text-background-color': '#FFFFFF',
            'text-background-opacity': 0.96,
            'text-background-padding': 2,
            'text-rotation': 'autorotate',
            'line-cap': 'round',
          },
        },
        {
          selector: 'edge[linkageBasis = "CASE_REFERENCE"]',
          style: { 'line-color': '#B91C1C', 'target-arrow-color': '#B91C1C', width: 3 },
        },
        {
          selector: 'edge[linkageBasis = "CHRONOLOGICALLY_REACHABLE"]',
          style: { 'line-color': '#0F766E', 'target-arrow-color': '#0F766E', 'line-style': 'dashed', width: 2.5 },
        },
        {
          selector: 'edge[?isSourceTransaction]',
          style: { 'line-color': '#B91C1C', 'target-arrow-color': '#B91C1C', width: 4 },
        },
        {
          selector: ':selected',
          style: { 'border-width': 4, 'border-color': '#D97706', 'line-color': '#D97706', 'target-arrow-color': '#D97706' },
        },
      ],
      layout: {
        name: 'preset',
        positions: (node) => positions[node.id()],
        fit: true,
        padding: 45,
      },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    cy.on('tap', 'edge', (event) => {
      setSelectedTransactionId(String(event.target.data('transactionId')));
      setSelectedAccountId(null);
    });
    cy.on('tap', 'node', (event) => {
      setSelectedAccountId(String(event.target.id()));
      setSelectedTransactionId(null);
    });
    cyInstanceRef.current = cy;
    return () => {
      cy.destroy();
      if (cyInstanceRef.current === cy) cyInstanceRef.current = null;
    };
  }, [graphData]);

  useEffect(() => {
    const cy = cyInstanceRef.current;
    if (!cy) return;
    cy.elements().unselect();
    if (selectedTransactionId) {
      const item = cy.getElementById(selectedTransactionId);
      if (item.length) item.select();
    }
    if (selectedAccountId) {
      const item = cy.getElementById(selectedAccountId);
      if (item.length) item.select();
    }
  }, [selectedTransactionId, selectedAccountId]);

  const resetView = () => {
    cyInstanceRef.current?.fit(undefined, 45);
    cyInstanceRef.current?.center();
  };

  const selectEdge = (edge: GraphEdge) => {
    setSelectedTransactionId(edge.id);
    setSelectedAccountId(null);
  };

  return (
    <div className="mx-auto max-w-[1600px] space-y-5">
      <section className="surface p-5 md:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="eyebrow flex items-center gap-2"><Waypoints size={13} /> Investigation / Fund flow</div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#24332d]">Reconstruct the movement of funds</h1>
            <p className="mt-2 text-sm leading-6 text-[#67756d]">
              Start from the case's source transaction, follow later debits from reached accounts, and compare account-level attribution ranges separately.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[230px] flex-1 text-xs font-semibold text-[#64736a]">
              Investigation case
              <select
                className="mt-1.5 w-full rounded-md border border-[#d8ded8] bg-white px-3 py-2.5 text-sm font-medium text-[#24332d] outline-none focus:border-[#477d69]"
                value={selectedCaseId}
                onChange={(event) => setSelectedCaseId(event.target.value)}
                disabled={loadingCases || cases.length === 0}
              >
                {cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {formatLabel(item.status)}</option>)}
              </select>
            </label>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-md border border-[#d8ded8] bg-white px-3 py-2.5 text-sm font-medium text-[#35443c] hover:bg-[#f3f5f0] disabled:opacity-50"
              onClick={() => setRefreshKey((value) => value + 1)}
              disabled={loadingFlow || loadingCases}
            >
              <RefreshCw size={14} className={loadingFlow ? 'animate-spin' : ''} /> Refresh ledger
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#e8ebe5] pt-3 text-xs text-[#637168]">
          <span className="inline-flex items-center gap-1.5 rounded bg-[#edf4ef] px-2 py-1 text-[#335b49]"><CheckCircle2 size={12} /> Local ledger-backed reconstruction</span>
          <span className="inline-flex items-center gap-1.5 rounded bg-[#f6f2e8] px-2 py-1 text-[#7a5b25]"><AlertTriangle size={12} /> Synthetic demonstration records; no live bank feed</span>
        </div>
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <div><div className="font-semibold">Could not reconstruct this case</div><div className="mt-1">{error}</div></div>
        </div>
      )}

      {loadingFlow ? (
        <section className="surface flex min-h-64 items-center justify-center gap-3 p-8 text-sm text-[#64736a]"><RefreshCw size={17} className="animate-spin" /> Reading the selected case and computing tracing estimates…</section>
      ) : graphData && consensus && selectedCase ? (
        <>
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article className="surface p-4">
              <div className="eyebrow">Source event</div>
              <div className="mt-2 font-mono text-lg font-semibold text-[#24332d]">{graphData.source_transaction_id ?? sourceEdge?.id ?? 'Unavailable'}</div>
              <div className="mt-1 text-xs text-[#718078]">Original ledger transaction · {formatINR(graphData.source_amount_inr ?? sourceEdge?.amount_inr ?? 0)}</div>
            </article>
            <article className="surface p-4">
              <div className="eyebrow">Candidate flow graph</div>
              <div className="mt-2 text-2xl font-semibold text-[#24332d]">{graphData.total_edges.toLocaleString('en-IN')} <span className="text-sm font-normal text-[#718078]">transactions</span></div>
              <div className="mt-1 text-xs text-[#718078]">{graphData.total_nodes.toLocaleString('en-IN')} accounts / counterparties · up to {hopCount} hops</div>
            </article>
            <article className="surface p-4">
              <div className="eyebrow">Evidence linkage</div>
              <div className="mt-2 text-2xl font-semibold text-[#24332d]">{referenceCount} <span className="text-sm font-normal text-[#718078]">case-linked</span></div>
              <div className="mt-1 text-xs text-[#718078]">{temporalCount} additional chronologically reachable records</div>
            </article>
            <article className="surface p-4">
              <div className="eyebrow">Consensus Lien comparison</div>
              {consensus.consensus_status === 'COMPARABLE' ? (
                <>
                  <div className="mt-2 text-lg font-semibold text-[#24332d]">{formatINR(consensus.total_lower_bound_inr)} – {formatINR(consensus.total_upper_bound_inr)}</div>
                  <div className="mt-1 text-xs text-[#718078]">Disagreement {formatINR(consensus.total_disagreement_inr)}</div>
                </>
              ) : (
                <div className="mt-2 text-sm font-semibold text-amber-800">Not comparable · figures withheld</div>
              )}
            </article>
          </section>

          <section className="surface overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-[#e7ebe5] p-4 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-base font-semibold text-[#24332d]">Directed movement graph</h2>
                <p className="mt-1 text-xs text-[#718078]">Each arrow is a recorded transaction. Select an arrow to cross-reference its event below.</p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-[#637168]">
                <span className="flex items-center gap-1.5"><span className="h-2 w-6 rounded bg-[#b91c1c]" /> Source / case-linked</span>
                <span className="flex items-center gap-1.5"><span className="h-0 w-6 border-t-2 border-dashed border-[#0f766e]" /> Chronologically reachable</span>
                <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded border border-[#c2410c] bg-[#fff7ed]" /> External / unknown account</span>
                <button type="button" className="ml-auto inline-flex items-center gap-1 rounded border border-[#d8ded8] px-2 py-1 hover:bg-[#f3f5f0]" onClick={resetView}>Fit graph</button>
              </div>
            </div>
            {graphData.nodes.length > 0 && graphData.edges.length > 0 ? (
              <div ref={cyContainerRef} className="h-[520px] w-full bg-[#fbfcfa]" aria-label="Directed case transaction flow graph" />
            ) : (
              <div className="p-12 text-center text-sm text-[#718078]">No source-linked transaction path is available for this case.</div>
            )}
            <div className="border-t border-[#e7ebe5] bg-[#fafbf8] px-4 py-3 text-xs leading-5 text-[#67756d]">
              {graphData.flow_scope || 'Graph scope comes from the case-linked ledger records.'}
              <span className="mt-1 block font-semibold text-[#805c22]">Important: arrow labels show full recorded transaction amounts, not the amount of the original source funds proven to be present in that transaction.</span>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
            <div className="surface overflow-hidden">
              <div className="border-b border-[#e7ebe5] p-4">
                <h2 className="text-base font-semibold text-[#24332d]">Chronological event trail</h2>
                <p className="mt-1 text-xs text-[#718078]">Ordered by the timestamps in the supplied ledger. Click a record to select the matching arrow.</p>
              </div>
              <div className="divide-y divide-[#edf0eb]">
                {edges.map((edge, index) => (
                  <button
                    type="button"
                    key={edge.id}
                    onClick={() => selectEdge(edge)}
                    className={`grid w-full grid-cols-[32px_minmax(0,1fr)_auto] gap-3 p-4 text-left transition-colors hover:bg-[#f7f9f5] ${selectedTransactionId === edge.id ? 'bg-[#eef5ef]' : 'bg-white'}`}
                  >
                    <span className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold ${edge.is_source_transaction ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-[#dce4dc] bg-[#f7f9f6] text-[#65736a]'}`}>
                      {edge.flow_hop ?? index + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold text-[#24332d]">{edge.id}</span>
                        <Badge variant={basisVariant(edge)} size="sm">{basisLabel(edge)}</Badge>
                        <Badge variant={edge.evidence_status === 'suspected_fraud' ? 'danger' : 'neutral'} size="sm">{formatLabel(edge.evidence_status || 'unflagged')}</Badge>
                      </span>
                      <span className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#43544a]">
                        <span className="break-all">{edge.source}</span><ArrowRight size={12} className="shrink-0 text-[#8a978e]" /><span className="break-all">{edge.target}</span>
                      </span>
                      <span className="mt-1.5 block text-[11px] text-[#879187]">{formatTime(edge.timestamp)} · {formatLabel(edge.transaction_type)}</span>
                    </span>
                    <span className="whitespace-nowrap text-right font-mono text-sm font-semibold text-[#24332d]">{formatINR(edge.amount_inr)}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-5">
              <section className="surface p-4">
                <h2 className="text-base font-semibold text-[#24332d]">Selected record</h2>
                {selectedEdge ? (
                  <div className="mt-4 space-y-3 text-sm">
                    <div className="rounded-md border border-[#e4e9e2] bg-[#fafbf8] p-3">
                      <div className="eyebrow">Transaction ID</div>
                      <div className="mt-1 font-mono font-semibold text-[#24332d]">{selectedEdge.id}</div>
                      <div className="mt-2 text-xs text-[#718078]">{formatTime(selectedEdge.timestamp)}</div>
                    </div>
                    <div className="flex items-start justify-between gap-4 border-b border-[#edf0eb] pb-2"><span className="text-xs text-[#718078]">Recorded amount</span><span className="font-mono font-semibold text-[#24332d]">{formatINR(selectedEdge.amount_inr)}</span></div>
                    <div className="flex items-start justify-between gap-4 border-b border-[#edf0eb] pb-2"><span className="text-xs text-[#718078]">Type</span><span className="text-right text-xs font-medium text-[#43544a]">{formatLabel(selectedEdge.transaction_type)}</span></div>
                    <div className="flex items-start justify-between gap-4 border-b border-[#edf0eb] pb-2"><span className="text-xs text-[#718078]">Linked by</span><span className="text-right text-xs font-medium text-[#43544a]">{basisLabel(selectedEdge)}</span></div>
                    <div className="flex items-start justify-between gap-4 border-b border-[#edf0eb] pb-2"><span className="text-xs text-[#718078]">Case reference</span><span className="break-all text-right font-mono text-xs text-[#43544a]">{selectedEdge.case_id || 'No direct case ID on this row'}</span></div>
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
                      A chronologically reachable debit is a follow-up candidate. It is not proof that the complete recorded amount contains funds from the original source transaction.
                    </div>
                  </div>
                ) : selectedNode ? (
                  <div className="mt-4 space-y-3 text-sm">
                    <div className="rounded-md border border-[#e4e9e2] bg-[#fafbf8] p-3"><div className="eyebrow">Account / counterparty</div><div className="mt-1 break-all font-mono font-semibold text-[#24332d]">{selectedNode.id}</div><div className="mt-1 text-xs text-[#718078]">{formatLabel(selectedNode.type)} · Flow level {selectedNode.flow_level ?? 'unknown'}</div></div>
                    <div className="flex justify-between gap-3 border-b border-[#edf0eb] pb-2 text-xs"><span className="text-[#718078]">Statement history</span><span className="font-medium text-[#43544a]">{selectedNode.history_complete == null ? 'Unknown in this scope' : selectedNode.history_complete ? 'Marked complete' : 'Incomplete'}</span></div>
                    <div className="flex justify-between gap-3 border-b border-[#edf0eb] pb-2 text-xs"><span className="text-[#718078]">End-of-ledger balance</span><span className="font-mono font-medium text-[#43544a]">{selectedNode.final_balance_inr == null ? 'Unavailable' : formatINR(selectedNode.final_balance_inr)}</span></div>
                    {lienByAccount.get(selectedNode.id) ? (
                      <div className="space-y-2 rounded-md border border-[#dbe6dc] bg-[#f6f9f4] p-3">
                        <div className="text-xs font-semibold text-[#354b3e]">Consensus Lien · account attribution</div>
                        <div className="grid grid-cols-2 gap-2 text-xs"><div><div className="text-[#718078]">Lower estimate</div><div className="mt-1 font-mono font-semibold">{formatINR(lienByAccount.get(selectedNode.id)!.lower_bound_inr)}</div></div><div><div className="text-[#718078]">Upper estimate</div><div className="mt-1 font-mono font-semibold">{formatINR(lienByAccount.get(selectedNode.id)!.upper_bound_inr)}</div></div></div>
                        <div className="text-[11px] text-[#718078]">Method disagreement: {formatINR(lienByAccount.get(selectedNode.id)!.disagreement_inr)}</div>
                      </div>
                    ) : <div className="rounded-md border border-[#e4e9e2] p-3 text-xs leading-5 text-[#718078]">No retained-balance estimate was returned for this account by the current tracing methods. This is not the same as a zero balance.</div>}
                  </div>
                ) : (
                  <div className="mt-4 py-8 text-center text-sm text-[#718078]">Select a node or transaction arrow to inspect the corresponding ledger evidence.</div>
                )}
              </section>

              <section className="surface p-4">
                <div className="flex items-center gap-2"><CircleDollarSign size={17} className="text-[#477d69]" /><h2 className="text-base font-semibold text-[#24332d]">Consensus Lien range</h2></div>
                {consensus.consensus_status === 'COMPARABLE' ? (
                  <div className="mt-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-md bg-[#f3f6f0] p-3"><div className="text-[10px] font-semibold uppercase tracking-wide text-[#718078]">Lower estimate</div><div className="mt-1 font-mono text-sm font-semibold text-[#24332d]">{formatINR(consensus.total_lower_bound_inr)}</div></div>
                      <div className="rounded-md bg-[#f3f6f0] p-3"><div className="text-[10px] font-semibold uppercase tracking-wide text-[#718078]">Upper estimate</div><div className="mt-1 font-mono text-sm font-semibold text-[#24332d]">{formatINR(consensus.total_upper_bound_inr)}</div></div>
                    </div>
                    <div className="flex items-center justify-between border-b border-[#edf0eb] pb-2 text-xs"><span className="text-[#718078]">Method disagreement</span><span className="font-mono font-semibold text-amber-800">{formatINR(consensus.total_disagreement_inr)}</span></div>
                    {(['proportional', 'fifo', 'libr'] as const).map((method) => (
                      <div key={method} className="rounded border border-[#e7ebe5] p-2.5">
                        <div className="font-semibold text-xs text-[#35443c]">{formatLabel(method)}</div>
                        <p className="mt-1 text-[11px] leading-4 text-[#718078]">{consensus.method_details[method].assumption}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">The tracing methods did not produce comparable results for this case. A range is withheld instead of displaying zeros as if they were valid.</div>
                )}
                <p className="mt-3 text-[11px] leading-5 text-[#718078]">The range compares modelled attribution assumptions. It is not a legal lien, a guaranteed recovery amount, or an instruction to freeze funds.</p>
              </section>
            </div>
          </section>
        </>
      ) : !loadingCases ? (
        <section className="surface p-10 text-center">
          <ShieldAlert size={22} className="mx-auto text-[#8a6d33]" />
          <h2 className="mt-3 text-base font-semibold text-[#24332d]">No case available for this identity</h2>
          <p className="mt-1 text-sm text-[#718078]">The case list endpoint returned no authorized cases.</p>
        </section>
      ) : null}
    </div>
  );
};

export default MoneyFlow;
