import React, { useCallback, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { Activity, BriefcaseBusiness, LoaderCircle, ShieldAlert } from 'lucide-react';
import { apiClient, DEMO_TOKEN_KEY } from './api/client';
import { Sidebar } from './components/layout/Sidebar';
import { Navbar } from './components/layout/Navbar';
import { Overview } from './pages/Overview';
import { TransactionExplorer } from './pages/TransactionExplorer';
import { MoneyFlow } from './pages/MoneyFlow';
import { ConsensusLien } from './pages/ConsensusLien';
import { InvestigationReview } from './pages/InvestigationReview';
import { DataQuality } from './pages/DataQuality';
import { MLAnalysis } from './pages/MLAnalysis';
import { TraceProof } from './pages/TraceProof';
import { SecurityAudit } from './pages/SecurityAudit';

interface DemoPersona {
  persona_id: string;
  display_name: string;
  role: string;
  assigned_case_count: number;
  institution_id: string;
}

interface AuthStatus {
  env_mode: string;
  demo_auth_enabled: boolean;
  production_auth_ready: boolean;
  auth_provider: string;
  message: string;
}

interface Session {
  mode: string;
  user: {
    user_id: string;
    display_name: string;
    role: string;
    institution_id: string;
    assigned_case_count: number;
  };
}

const PAGE_META: Record<string, { title: string; subtitle: string; section: string }> = {
  '/': { title: 'Case overview', subtitle: 'Review the current analytical ledger and open investigations.', section: 'Workspace' },
  '/explorer': { title: 'Transaction explorer', subtitle: 'Inspect source records, filters and account balance history.', section: 'Investigation' },
  '/money-flow': { title: 'Money flow reconstruction', subtitle: 'Follow case-linked transactions and chronologically reachable account activity.', section: 'Investigation' },
  '/consensus-lien': { title: 'Fund tracing comparison', subtitle: 'Compare proportional, FIFO and LIBR attribution assumptions.', section: 'Analysis' },
  '/traceproof': { title: 'TraceProof', subtitle: 'Inspect source-attested links across simulated financial rails.', section: 'Investigation' },
  '/investigation': { title: 'Case review', subtitle: 'Review the records supporting an investigation-priority assessment.', section: 'Investigation' },
  '/ml-analysis': { title: 'Model evaluation', subtitle: 'Actual training metadata, held-out metrics and model inference.', section: 'Machine learning' },
  '/data-quality': { title: 'Data quality', subtitle: 'Files found, observed row counts, schema validation and data gaps.', section: 'Governance' },
  '/security': { title: 'Security review', subtitle: 'Runtime identity mode, verification results and audit events.', section: 'Governance' },
};

interface AppContentProps {
  session: Session;
  personas: DemoPersona[];
  onSelectPersona: (personaId: string) => Promise<void>;
  onSignOut: () => void;
}

const AppContent: React.FC<AppContentProps> = ({ session, personas, onSelectPersona, onSignOut }) => {
  const location = useLocation();
  const page = PAGE_META[location.pathname] ?? PAGE_META['/'];
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="workspace">
        <Navbar
          title={page.title}
          subtitle={page.subtitle}
          section={page.section}
          currentUser={session.user}
          personas={personas}
          onSelectPersona={onSelectPersona}
          onSignOut={onSignOut}
        />
        <main className="workspace-main" key={session.user.user_id}>
          <div className="page-width">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/explorer" element={<TransactionExplorer />} />
              <Route path="/money-flow" element={<MoneyFlow />} />
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

const AuthGate: React.FC = () => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [personas, setPersonas] = useState<DemoPersona[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyPersona, setBusyPersona] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    const response = await apiClient.get<Session>('/api/auth/session');
    setSession(response.data);
  }, []);

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      setLoading(true);
      setError(null);
      try {
        const statusResponse = await apiClient.get<AuthStatus>('/api/auth/status');
        if (!active) return;
        setAuthStatus(statusResponse.data);

        if (statusResponse.data.demo_auth_enabled) {
          const personaResponse = await apiClient.get<{ mode: string; personas: DemoPersona[] }>('/api/auth/personas');
          if (!active) return;
          setPersonas(personaResponse.data.personas);
        }

        if (window.localStorage.getItem(DEMO_TOKEN_KEY)) {
          try {
            await loadSession();
          } catch {
            window.localStorage.removeItem(DEMO_TOKEN_KEY);
            if (active) setSession(null);
          }
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Unable to reach the authentication endpoint.');
      } finally {
        if (active) setLoading(false);
      }
    };
    bootstrap();
    return () => { active = false; };
  }, [loadSession]);

  const selectPersona = useCallback(async (personaId: string) => {
    setBusyPersona(personaId);
    setError(null);
    const previousToken = window.localStorage.getItem(DEMO_TOKEN_KEY);
    try {
      // Session issuance is explicitly limited to local demo mode by the backend.
      const result = await apiClient.post<{ token: string; user: Session['user']; mode: string }>(
        '/api/auth/demo-session',
        { persona_id: personaId },
      );
      window.localStorage.setItem(DEMO_TOKEN_KEY, result.data.token);
      const confirmed = await apiClient.get<Session>('/api/auth/session');
      setSession(confirmed.data);
      window.dispatchEvent(new Event('auth-changed'));
    } catch (cause) {
      if (previousToken) window.localStorage.setItem(DEMO_TOKEN_KEY, previousToken);
      else window.localStorage.removeItem(DEMO_TOKEN_KEY);
      setError(cause instanceof Error ? cause.message : 'Could not start the selected demonstration session.');
    } finally {
      setBusyPersona(null);
    }
  }, []);

  const signOut = useCallback(() => {
    window.localStorage.removeItem(DEMO_TOKEN_KEY);
    setSession(null);
    setError(null);
    window.dispatchEvent(new Event('auth-changed'));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f4ef] px-6">
        <div className="flex items-center gap-3 text-sm text-slate-600"><LoaderCircle size={18} className="animate-spin" /> Checking API and identity configuration…</div>
      </div>
    );
  }

  if (session) {
    return (
      <Router>
        <div className="relative">
          <AppContent session={session} personas={personas} onSelectPersona={selectPersona} onSignOut={signOut} />

        </div>
      </Router>
    );
  }

  return (
    <div className="min-h-screen bg-[#f4f4ef] px-5 py-10 flex items-center justify-center">
      <div className="w-full max-w-3xl">
        <div className="eyebrow">FAIRHOLD / ACCESS</div>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#24332d]">Enter the investigation workspace</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[#7a837a]">Protected pages are not loaded until the backend confirms a session. Local personas are demonstration identities, not real institutional authentication.</p>

        {error && <div className="fh-error mt-5">{error}</div>}

        {authStatus?.demo_auth_enabled ? (
          <div className="mt-7 grid gap-3 md:grid-cols-2">
            {personas.map((persona) => (
              <button
                key={persona.persona_id}
                type="button"
                disabled={busyPersona !== null}
                onClick={() => void selectPersona(persona.persona_id)}
                className="surface p-5 text-left transition-colors hover:bg-[#f0f2eb] disabled:opacity-60"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-[#2d3b32]">{persona.display_name}</div>
                    <div className="mt-1 text-xs text-[#7d8580]">{persona.role}</div>
                  </div>
                  <div className="rounded-md bg-[#e9f0eb] p-2 text-[#1f4a40]">
                    {persona.role.toLowerCase().includes('admin') ? <ShieldAlert size={17} /> : <Activity size={17} />}
                  </div>
                </div>
                <div className="mt-4 border-t border-[#e2e4dc] pt-3 text-xs text-[#7d8580]">
                  {persona.assigned_case_count} assigned cases · {persona.institution_id}
                </div>
                <div className="mt-3 text-xs font-semibold text-[#1f4a40]">{busyPersona === persona.persona_id ? 'Starting session…' : 'Enter demo workspace →'}</div>
              </button>
            ))}
          </div>
        ) : (
          <div className="mt-7 surface p-5">
            <div className="flex items-start gap-3">
              <BriefcaseBusiness size={20} className="mt-0.5 text-[#8b6b3f]" />
              <div>
                <h2 className="font-semibold text-[#2d3b32]">No identity provider is configured</h2>
                <p className="mt-1 text-sm leading-6 text-[#7a837a]">{authStatus?.message || 'The application intentionally blocks protected pages because production OIDC verification has not been implemented.'}</p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-7 border-t border-[#e2e4dc] pt-4 text-xs leading-5 text-[#92988e]">
          Local demo mode uses mock roles and synthetic investigation data. Do not use it with real banking data or describe it as production authentication.
        </div>
      </div>
    </div>
  );
};

export const App: React.FC = () => <AuthGate />;
export default App;
