import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { Sidebar } from './components/layout/Sidebar';
import { Navbar } from './components/layout/Navbar';
import { Overview } from './pages/Overview';
import { TransactionExplorer } from './pages/TransactionExplorer';
import { ConsensusLien } from './pages/ConsensusLien';
import { InvestigationReview } from './pages/InvestigationReview';
import { DataQuality } from './pages/DataQuality';
import { MLAnalysis } from './pages/MLAnalysis';
import { TraceProof } from './pages/TraceProof';
import { SecurityAudit } from './pages/SecurityAudit';

const AppContent: React.FC = () => {
  const location = useLocation();

  const getPageTitle = (pathname: string): { title: string; subtitle: string } => {
    switch (pathname) {
      case '/':
        return {
          title: 'Investigation Overview',
          subtitle: 'System health, ledger integrity, and triage queues',
        };
      case '/explorer':
        return {
          title: 'Transaction Explorer & Graph',
          subtitle: 'Multi-hop fund transfer flows, graph topology, and balance timelines',
        };
      case '/consensus-lien':
        return {
          title: 'Consensus Lien Comparison',
          subtitle: 'Proportional vs. FIFO vs. LIBR method bounds and divergence drivers',
        };
      case '/traceproof':
        return {
          title: 'TraceProof Multi-Rail Reconstruction',
          subtitle: 'Cryptographically verified cross-institution path across Bank A, Wallet B, and Bank C',
        };
      case '/investigation':
        return {
          title: 'Investigation Priority Review',
          subtitle: 'Explainable prioritization score and structured evidence breakdown',
        };
      case '/ml-analysis':
        return {
          title: 'ML Transaction Fraud Classifier',
          subtitle: 'European credit card fraud benchmark model and real test vector prediction',
        };
      case '/data-quality':
        return {
          title: 'Data Quality & Hygiene Audit',
          subtitle: 'Dataset inventory, schema checks, and ground-truth isolation status',
        };
      case '/security':
        return {
          title: 'Security Governance & Audit Trail',
          subtitle: 'Zero-trust BOLA boundaries, PKI cryptographic envelopes, and immutable audit logs',
        };
      default:
        return {
          title: 'Smart-Freeze',
          subtitle: 'Fraud Investigation Decision Support',
        };
    }
  };

  const { title, subtitle } = getPageTitle(location.pathname);

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-800">
      {/* Dark Navy Sidebar */}
      <Sidebar />

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Navbar */}
        <Navbar title={title} subtitle={subtitle} />

        {/* Scrollable Page Body */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/explorer" element={<TransactionExplorer />} />
            <Route path="/consensus-lien" element={<ConsensusLien />} />
            <Route path="/traceproof" element={<TraceProof />} />
            <Route path="/investigation" element={<InvestigationReview />} />
            <Route path="/ml-analysis" element={<MLAnalysis />} />
            <Route path="/data-quality" element={<DataQuality />} />
            <Route path="/security" element={<SecurityAudit />} />
          </Routes>
        </main>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <Router>
      <AppContent />
    </Router>
  );
};

export default App;
