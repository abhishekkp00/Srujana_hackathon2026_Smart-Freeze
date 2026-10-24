import React, { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import {
  Search,
  TrendingUp,
  Layers,
  X,
  RefreshCw,
} from 'lucide-react';
import {
  getTransactions,
  getCases,
  getAccounts,
  getAccountBalanceHistory,
  getGraphData,
} from '../api/endpoints';
import {
  TransactionItem,
  CaseSummary,
  AccountItem,
  BalanceEventItem,
  GraphData,
} from '../types';
import { Badge } from '../components/common/Badge';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

export const TransactionExplorer: React.FC = () => {
  // Data states
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [totalTransactions, setTotalTransactions] = useState(0);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [graphData, setGraphData] = useState<GraphData | null>(null);

  // Filter states
  const [selectedCaseId, setSelectedCaseId] = useState<string>('');
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(0);
  const limit = 20;

  // Selection states
  const [selectedTx, setSelectedTx] = useState<TransactionItem | null>(null);
  const [selectedGraphElement, setSelectedGraphElement] = useState<{
    type: 'node' | 'edge';
    data: any;
  } | null>(null);
  const [balanceHistory, setBalanceHistory] = useState<BalanceEventItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Graph DOM container ref
  const cyContainerRef = useRef<HTMLDivElement>(null);
  const cyInstanceRef = useRef<cytoscape.Core | null>(null);

  // Loading states
  const [loading, setLoading] = useState(true);

  // Load only cases visible to the active identity. Account inventory is case-scoped.
  useEffect(() => {
    const fetchCases = async () => {
      try {
        const cList = await getCases();
        setCases(cList);
        setSelectedCaseId((current) => current && cList.some((item) => item.case_id === current) ? current : (cList[0]?.case_id ?? ''));
      } catch (err) {
        console.error('Failed to load authorized cases:', err);
        setCases([]);
        setSelectedCaseId('');
      }
    };
    fetchCases();
    const handleAuthChange = () => { fetchCases(); };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => window.removeEventListener('auth-changed', handleAuthChange);
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      setAccounts([]);
      return;
    }
    getAccounts(selectedCaseId).then(setAccounts).catch((err) => {
      setAccounts([]);
      console.error('Failed to load accounts for selected case:', err);
    });
  }, [selectedCaseId]);

  // Fetch transactions and graph data when filters change
  useEffect(() => {
    const fetchData = async () => {
      if (!selectedCaseId) {
        setTransactions([]);
        setTotalTransactions(0);
        setGraphData(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const [txData, gData] = await Promise.all([
          getTransactions({
            case_id: selectedCaseId || undefined,
            account_id: selectedAccountId || undefined,
            transaction_type: typeFilter || undefined,
            evidence_status: statusFilter || undefined,
            search: searchQuery || undefined,
            limit,
            offset: page * limit,
          }),
          getGraphData(selectedCaseId || undefined),
        ]);
        setTransactions(txData.items);
        setTotalTransactions(txData.total);
        setGraphData(gData);
      } catch (err) {
        console.error('Failed to fetch transaction data:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedCaseId, selectedAccountId, typeFilter, statusFilter, searchQuery, page]);

  // Fetch account balance history when an account is selected
  useEffect(() => {
    if (!selectedAccountId) {
      setBalanceHistory([]);
      return;
    }
    const fetchHistory = async () => {
      setHistoryLoading(true);
      try {
        const data = await getAccountBalanceHistory(selectedAccountId, selectedCaseId);
        setBalanceHistory(data);
      } catch (err) {
        console.error('Failed to load balance history:', err);
        setBalanceHistory([]);
      } finally {
        setHistoryLoading(false);
      }
    };
    fetchHistory();
  }, [selectedAccountId]);

  // Cytoscape initialization and updates
  useEffect(() => {
    if (!cyContainerRef.current || !graphData) return;

    // Destroy existing instance
    if (cyInstanceRef.current) {
      cyInstanceRef.current.destroy();
    }

    const elements: cytoscape.ElementDefinition[] = [];

    // Add nodes
    graphData.nodes.forEach((n) => {
      elements.push({
        group: 'nodes',
        data: {
          id: n.id,
          label: n.label,
          type: n.type,
          isExternal: n.is_external,
          historyComplete: n.history_complete,
          finalBalanceInr: n.final_balance_inr,
        },
      });
    });

    // Add edges
    graphData.edges.forEach((e) => {
      elements.push({
        group: 'edges',
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          amountInr: e.amount_inr,
          transactionType: e.transaction_type,
          evidenceStatus: e.evidence_status,
          timestamp: e.timestamp,
        },
      });
    });

    const cy = cytoscape({
      container: cyContainerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-size': '11px',
            'font-weight': 'bold',
            color: '#1E293B',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'background-color': '#0284C7',
            width: 38,
            height: 38,
            'border-width': 2,
            'border-color': '#0369A1',
          },
        },
        {
          selector: 'node[?isExternal]',
          style: {
            'background-color': '#F59E0B',
            'border-color': '#D97706',
            shape: 'rectangle',
            width: 44,
            height: 32,
          },
        },
        {
          selector: 'node[!historyComplete]',
          style: {
            'border-style': 'dashed',
            'border-color': '#EF4444',
            'border-width': 3,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 2.5,
            'line-color': '#94A3B8',
            'target-arrow-color': '#64748B',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: (ele: any) => `₹${ele.data('amountInr').toLocaleString('en-IN')}`,
            'font-size': '10px',
            'text-background-color': '#FFFFFF',
            'text-background-opacity': 0.85,
            'text-background-padding': '2px',
            color: '#334155',
          },
        },
        {
          selector: 'edge[evidenceStatus = "suspected_fraud"]',
          style: {
            'line-color': '#E11D48',
            'target-arrow-color': '#E11D48',
            width: 3,
          },
        },
        {
          selector: ':selected',
          style: {
            'border-width': 4,
            'border-color': '#10B981',
            'line-color': '#10B981',
            'target-arrow-color': '#10B981',
          },
        },
      ],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 40,
        spacingFactor: 1.4,
      },
    });

    // Click handlers
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      setSelectedGraphElement({ type: 'node', data: node.data() });
      setSelectedAccountId(node.data('id'));
    });

    cy.on('tap', 'edge', (evt) => {
      const edge = evt.target;
      setSelectedGraphElement({ type: 'edge', data: edge.data() });
    });

    cyInstanceRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [graphData]);

  // Chart data for Balance History
  const balanceChartData = balanceHistory.map((ev, idx) => ({
    index: idx + 1,
    timestamp: ev.timestamp.split('T')[1]?.replace('Z', '') || ev.timestamp,
    balance: ev.balance_after_inr,
    change: ev.amount_change_inr,
    txId: ev.transaction_id,
  }));

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header & Filter Controls */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Transaction Explorer & Graph</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Inspect multi-hop transfers, interactive directed graph paths, and running account balance events.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => {
                setSelectedCaseId('');
                setSelectedAccountId('');
                setTypeFilter('');
                setStatusFilter('');
                setSearchQuery('');
              }}
              className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors flex items-center"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
              Reset Filters
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 pt-2">
          {/* Case Selector */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Filter by Case</label>
            <select
              value={selectedCaseId}
              onChange={(e) => {
                setSelectedCaseId(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500"
            >
              <option value="">All Cases</option>
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id}
                </option>
              ))}
            </select>
          </div>

          {/* Account Selector */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Filter by Account</label>
            <select
              value={selectedAccountId}
              onChange={(e) => {
                setSelectedAccountId(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500"
            >
              <option value="">All Accounts</option>
              {accounts.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.account_id} {!a.history_complete ? '(!)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Transaction Type Filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Type</label>
            <select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500"
            >
              <option value="">All Types</option>
              <option value="transfer">transfer</option>
              <option value="withdrawal">withdrawal</option>
              <option value="deposit">deposit</option>
              <option value="salary_credit">salary_credit</option>
              <option value="merchant_payment">merchant_payment</option>
            </select>
          </div>

          {/* Evidence Status */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Evidence Status</label>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500"
            >
              <option value="">All Statuses</option>
              <option value="suspected_fraud">suspected_fraud</option>
              <option value="verified_legitimate">verified_legitimate</option>
              <option value="unflagged">unflagged</option>
            </select>
          </div>

          {/* Search Query */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">Search ID / Account</label>
            <div className="relative">
              <input
                type="text"
                placeholder="TXN_0001, ACC_..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(0);
                }}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-3 py-1.5 text-xs font-medium text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Interactive Graph + Selection Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Cytoscape.js Directed Transaction Graph */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900 flex items-center">
                <Layers className="w-4 h-4 mr-1.5 text-teal-600" />
                Directed Multi-Hop Fund Flow Graph
              </h3>
              <p className="text-[11px] text-slate-500">
                Click any node or edge to inspect provenance, balances, and history. Red border indicates incomplete statement context.
              </p>
            </div>
            <div className="flex items-center space-x-3 text-xs text-slate-500">
              <span className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-sky-600 mr-1"></span>Internal</span>
              <span className="flex items-center"><span className="w-2.5 h-2.5 rounded bg-amber-500 mr-1"></span>External</span>
              <span className="flex items-center"><span className="w-2.5 h-0.5 bg-rose-600 mr-1"></span>Suspected</span>
            </div>
          </div>

          <div
            ref={cyContainerRef}
            className="w-full h-80 rounded-lg bg-slate-50 border border-slate-200/80 cursor-grab active:cursor-grabbing"
          />
        </div>

        {/* Selected Graph Element / Account Inspector */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <h3 className="text-sm font-bold text-slate-900">Entity & Flow Inspector</h3>
              {selectedGraphElement && (
                <button
                  onClick={() => setSelectedGraphElement(null)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {selectedGraphElement ? (
              <div className="space-y-3 text-xs">
                {selectedGraphElement.type === 'node' ? (
                  <>
                    <div className="p-3 bg-sky-50 border border-sky-100 rounded-lg">
                      <span className="text-[10px] font-bold text-sky-700 uppercase">Selected Account Node</span>
                      <div className="text-base font-bold text-sky-950 mt-0.5">{selectedGraphElement.data.id}</div>
                      <div className="text-xs text-sky-700 mt-1">
                        Type: <span className="font-semibold">{selectedGraphElement.data.type}</span>
                      </div>
                    </div>
                    <div className="space-y-1.5 pt-1">
                      <div className="flex justify-between py-1 border-b border-slate-100">
                        <span className="text-slate-500">Reconstructed Final Balance:</span>
                        <span className="font-bold text-slate-900">
                          ₹{Number(selectedGraphElement.data.finalBalanceInr || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-100">
                        <span className="text-slate-500">Statement Completeness:</span>
                        <span className={selectedGraphElement.data.historyComplete ? 'text-emerald-700 font-semibold' : 'text-rose-600 font-bold'}>
                          {selectedGraphElement.data.historyComplete ? 'Complete History' : 'Incomplete History (!)'}
                        </span>
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="p-3 bg-slate-50 border border-slate-100 rounded-lg">
                      <span className="text-[10px] font-bold text-slate-500 uppercase">Selected Transfer Edge</span>
                      <div className="text-base font-bold text-slate-900 mt-0.5">{selectedGraphElement.data.id}</div>
                      <div className="text-xs text-slate-600 mt-1">
                        {selectedGraphElement.data.source} → {selectedGraphElement.data.target}
                      </div>
                    </div>
                    <div className="space-y-1.5 pt-1">
                      <div className="flex justify-between py-1 border-b border-slate-100">
                        <span className="text-slate-500">Transfer Amount:</span>
                        <span className="font-bold text-slate-900">
                          ₹{Number(selectedGraphElement.data.amountInr || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-100">
                        <span className="text-slate-500">Evidence Status:</span>
                        <Badge variant={selectedGraphElement.data.evidenceStatus === 'suspected_fraud' ? 'danger' : 'neutral'} size="sm">
                          {selectedGraphElement.data.evidenceStatus}
                        </Badge>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-100">
                        <span className="text-slate-500">Timestamp:</span>
                        <span className="text-slate-700 font-mono text-[11px]">{selectedGraphElement.data.timestamp}</span>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-slate-400 text-xs">
                Click any node or transaction edge in the graph to view properties.
              </div>
            )}
          </div>

          {selectedAccountId && (
            <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-500 flex items-center justify-between">
              <span>Account balance events tracked below</span>
              <span className="font-mono text-slate-700 font-semibold">{selectedAccountId}</span>
            </div>
          )}
        </div>
      </div>

      {/* Account Balance History Timeline (Recharts) */}
      {selectedAccountId && (
        historyLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm text-center text-xs text-slate-500">
            Reconstructing chronological balance timeline for <span className="font-mono font-semibold">{selectedAccountId}</span>...
          </div>
        ) : balanceHistory.length > 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center">
                  <TrendingUp className="w-4 h-4 mr-1.5 text-teal-600" />
                  Chronological Balance History: <span className="ml-1 text-teal-800 font-mono">{selectedAccountId}</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Exact balance impact across sequentially reconstructed credits and debits.
                </p>
              </div>
              <span className="text-xs font-semibold px-2.5 py-1 rounded bg-slate-100 text-slate-600">
                {balanceHistory.length} Balance Events
              </span>
            </div>

            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={balanceChartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#64748B' }} />
                  <YAxis
                    tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                    tick={{ fontSize: 10, fill: '#64748B' }}
                  />
                  <Tooltip
                    formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, 'Running Balance']}
                    contentStyle={{ backgroundColor: '#FFFFFF', borderRadius: '8px', border: '1px solid #E2E8F0', fontSize: '11px' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="balance"
                    stroke="#0284C7"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: '#0369A1' }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : null
      )}

      {/* Validated Transactions Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Transaction Records</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Showing {transactions.length} of {totalTransactions} validated records in ledger
            </p>
          </div>
          {loading && (
            <span className="text-xs text-teal-600 font-medium flex items-center animate-pulse">
              Loading records...
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[11px] font-semibold">
              <tr>
                <th className="py-3 px-4">Transaction ID</th>
                <th className="py-3 px-4">Timestamp (UTC)</th>
                <th className="py-3 px-4">From Account</th>
                <th className="py-3 px-4">To Account</th>
                <th className="py-3 px-4">Amount (INR)</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4">Case ID</th>
                <th className="py-3 px-4">Evidence Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {transactions.map((tx) => (
                <tr
                  key={tx.transaction_id}
                  onClick={() => setSelectedTx(tx)}
                  className="hover:bg-slate-50/80 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4 font-mono font-bold text-slate-800">{tx.transaction_id}</td>
                  <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">{tx.timestamp}</td>
                  <td className="py-3 px-4 font-mono text-slate-700">{tx.from_account}</td>
                  <td className="py-3 px-4 font-mono text-slate-700">{tx.to_account}</td>
                  <td className="py-3 px-4 font-bold text-slate-900">
                    ₹{tx.amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-4">
                    <span className="capitalize text-slate-600">{tx.transaction_type.replace('_', ' ')}</span>
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-600">{tx.case_id || '—'}</td>
                  <td className="py-3 px-4">
                    <Badge variant={tx.evidence_status === 'suspected_fraud' ? 'danger' : 'neutral'} size="sm">
                      {tx.evidence_status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination controls */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-600">
          <span>Page {page + 1} of {Math.ceil(totalTransactions / limit) || 1}</span>
          <div className="flex space-x-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1.5 rounded bg-white border border-slate-200 disabled:opacity-40 font-medium hover:bg-slate-100"
            >
              Previous
            </button>
            <button
              disabled={(page + 1) * limit >= totalTransactions}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1.5 rounded bg-white border border-slate-200 disabled:opacity-40 font-medium hover:bg-slate-100"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Transaction Detail Drawer / Modal */}
      {selectedTx && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-base text-slate-900">Transaction Record Details</h3>
              <button onClick={() => setSelectedTx(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Transaction ID:</span>
                <span className="font-mono font-bold text-slate-800">{selectedTx.transaction_id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Timestamp:</span>
                <span className="font-mono text-slate-700">{selectedTx.timestamp}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">From Account:</span>
                <span className="font-mono font-semibold text-slate-800">{selectedTx.from_account}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">To Account:</span>
                <span className="font-mono font-semibold text-slate-800">{selectedTx.to_account}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Amount (INR):</span>
                <span className="font-bold text-slate-900 text-sm">
                  ₹{selectedTx.amount_inr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Amount (Paise):</span>
                <span className="font-mono text-slate-700">{selectedTx.amount_paise.toLocaleString()} paise</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Transaction Type:</span>
                <span className="capitalize font-semibold text-slate-800">{selectedTx.transaction_type}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-slate-100">
                <span className="text-slate-500">Evidence Status:</span>
                <Badge variant={selectedTx.evidence_status === 'suspected_fraud' ? 'danger' : 'neutral'}>
                  {selectedTx.evidence_status}
                </Badge>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedTx(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
