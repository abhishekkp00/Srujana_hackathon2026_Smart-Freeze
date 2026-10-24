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

const PAGE_META: Record<string, { title: string; subtitle: string; section: string }> = {
  '/': { title: 'Case overview', subtitle: 'A working view of the investigative queue and ledger integrity.', section: 'Workspace' },
  '/explorer': { title: 'Transaction explorer', subtitle: 'Follow transfer paths, account activity and balance changes.', section: 'Analysis' },
  '/consensus-lien': { title: 'Fund tracing comparison', subtitle: 'Compare proportional, FIFO and LIBR attribution assumptions.', section: 'Analysis' },
  '/traceproof': { title: 'TraceProof', subtitle: 'Evidence continuity across simulated financial rails.', section: 'Investigation' },
  '/investigation': { title: 'Case review', subtitle: 'Review the evidence behind an investigation-priority assessment.', section: 'Investigation' },
  '/ml-analysis': { title: 'Model evaluation', subtitle: 'Historical credit-card benchmark results and transaction inference.', section: 'Research' },
  '/data-quality': { title: 'Data quality', subtitle: 'Input coverage, validation findings and dataset provenance.', section: 'Governance' },
  '/security': { title: 'Security review', subtitle: 'Access boundaries, evidence verification and audit events.', section: 'Governance' },
};

const AppContent: React.FC = () => {
  const location = useLocation();
  const page = PAGE_META[location.pathname] ?? PAGE_META['/'];

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace">
        <Navbar title={page.title} subtitle={page.subtitle} section={page.section} />
        <main className="workspace-main">
          <div className="page-width">
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
          </div>
        </main>
      </div>
    </div>
  );
};

export const App: React.FC = () => <Router><AppContent /></Router>;
export default App;
