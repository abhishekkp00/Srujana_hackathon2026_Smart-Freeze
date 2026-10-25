import React, { useCallback, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { BriefcaseBusiness, LoaderCircle, ShieldCheck } from 'lucide-react';
import { apiClient, DEMO_TOKEN_KEY } from './api/client';
import { Sidebar } from './components/layout/Sidebar';
import { Navbar } from './components/layout/Navbar';
import { Overview } from './pages/Overview';
import { MoneyFlow } from './pages/MoneyFlow';
import { ConsensusLien } from './pages/ConsensusLien';

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
  '/': { title: 'Case overview', subtitle: 'Choose a case and follow the recorded money movement.', section: 'Workspace' },
  '/money-flow': { title: 'Money flow', subtitle: 'See where transactions move and where commingling may occur.', section: 'Investigation' },
  '/consensus-lien': { title: 'Consensus Lien', subtitle: 'Compare three tracing methods for the same selected case.', section: 'Analysis' },
};

interface AppContentProps {
  session: Session;
  onSignOut: () => void;
}

const AppContent: React.FC<AppContentProps> = ({ session, onSignOut }) => {
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
          onSignOut={onSignOut}
        />
        <main className="workspace-main" key={session.user.user_id}>
          <div className="page-width">
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/money-flow" element={<MoneyFlow />} />
              <Route path="/consensus-lien" element={<ConsensusLien />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
};

const AuthGate: React.FC = () => {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [demoPersona, setDemoPersona] = useState<DemoPersona | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
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
          const response = await apiClient.get<{ mode: string; personas: DemoPersona[] }>('/api/auth/personas');
          if (!active) return;
          setDemoPersona(response.data.personas[0] ?? null);
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
        if (active) setError(cause instanceof Error ? cause.message : 'Unable to reach the API.');
      } finally {
        if (active) setLoading(false);
      }
    };
    void bootstrap();
    return () => { active = false; };
  }, [loadSession]);

  const startDemoSession = useCallback(async () => {
    if (!demoPersona) return;
    setStarting(true);
    setError(null);
    try {
      const response = await apiClient.post<{ token: string }>('/api/auth/demo-session', {
        persona_id: demoPersona.persona_id,
      });
      window.localStorage.setItem(DEMO_TOKEN_KEY, response.data.token);
      await loadSession();
      window.dispatchEvent(new Event('auth-changed'));
    } catch (cause) {
      window.localStorage.removeItem(DEMO_TOKEN_KEY);
      setError(cause instanceof Error ? cause.message : 'Could not start the local demo session.');
    } finally {
      setStarting(false);
    }
  }, [demoPersona, loadSession]);

  const signOut = useCallback(() => {
    window.localStorage.removeItem(DEMO_TOKEN_KEY);
    setSession(null);
    setError(null);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f4ef] px-6">
        <div className="flex items-center gap-3 text-sm text-slate-600"><LoaderCircle size={18} className="animate-spin" /> Connecting to the local ledger…</div>
      </div>
    );
  }

  if (session) {
    return (
      <Router>
        <AppContent session={session} onSignOut={signOut} />
      </Router>
    );
  }

  return (
    <div className="min-h-screen bg-[#f4f4ef] px-5 py-10 flex items-center justify-center">
      <div className="w-full max-w-xl">
        <div className="eyebrow">FAIRHOLD / LOCAL DEMO</div>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#24332d]">Follow the money trail</h1>
        <p className="mt-2 text-sm leading-6 text-[#7a837a]">A single local demo identity is used to inspect the synthetic case ledger. This is not a live bank connection.</p>
        {error && <div className="fh-error mt-5">{error}</div>}

        {authStatus?.demo_auth_enabled && demoPersona ? (
          <div className="mt-6 surface p-5">
            <div className="flex items-start gap-3">
              <div className="rounded-md bg-[#e9f0eb] p-2 text-[#1f4a40]"><ShieldCheck size={18} /></div>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-[#2d3b32]">{demoPersona.display_name}</div>
                <div className="mt-1 text-xs text-[#7d8580]">{demoPersona.assigned_case_count} cases available from the local ledger</div>
              </div>
            </div>
            <button
              type="button"
              disabled={starting}
              onClick={() => void startDemoSession()}
              className="mt-5 w-full rounded-md bg-[#174b3b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0f3d2f] disabled:opacity-60"
            >
              {starting ? 'Starting demo…' : 'Enter FairHold'}
            </button>
          </div>
        ) : (
          <div className="mt-6 surface p-5">
            <div className="flex items-start gap-3">
              <BriefcaseBusiness size={20} className="mt-0.5 text-[#8b6b3f]" />
              <div>
                <h2 className="font-semibold text-[#2d3b32]">Local demo session is disabled</h2>
                <p className="mt-1 text-sm leading-6 text-[#7a837a]">{authStatus?.message || 'Start FastAPI with SMART_FREEZE_ENV=development and ENABLE_DEMO_AUTH=true.'}</p>
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 border-t border-[#e2e4dc] pt-3 text-xs leading-5 text-[#92988e]">
          Demo-only authentication · synthetic data · no production banking access
        </div>
      </div>
    </div>
  );
};

export const App: React.FC = () => <AuthGate />;
export default App;
