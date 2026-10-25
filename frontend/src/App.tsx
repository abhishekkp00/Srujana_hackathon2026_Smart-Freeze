import React, { useCallback, useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import { apiClient, DEMO_TOKEN_KEY } from './api/client';
import { Sidebar } from './components/layout/Sidebar';
import { Navbar } from './components/layout/Navbar';
import { Overview } from './pages/Overview';
import { MoneyFlow } from './pages/MoneyFlow';
import { ConsensusLien } from './pages/ConsensusLien';
import { LandingPage } from './pages/LandingPage';

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
  '/': { title: 'Dashboard', subtitle: 'Monitor cases, transaction activity and evidence.', section: 'Workspace' },
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
  const [showLanding, setShowLanding] = useState(true);
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
      setShowLanding(false);
      window.dispatchEvent(new Event('auth-changed'));
    } catch (cause) {
      window.localStorage.removeItem(DEMO_TOKEN_KEY);
      setError(cause instanceof Error ? cause.message : 'Could not start the local demo session.');
    } finally {
      setStarting(false);
    }
  }, [demoPersona, loadSession]);

  const enterWorkspace = useCallback(() => {
    if (session) {
      setShowLanding(false);
      return;
    }
    void startDemoSession();
  }, [session, startDemoSession]);

  const signOut = useCallback(() => {
    window.localStorage.removeItem(DEMO_TOKEN_KEY);
    setSession(null);
    setShowLanding(true);
    setError(null);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f4ef] px-6">
        <div className="flex items-center gap-3 text-sm text-slate-600"><LoaderCircle size={18} className="animate-spin" /> Connecting to the local ledger…</div>
      </div>
    );
  }

  if (session && !showLanding) {
    return (
      <Router>
        <AppContent session={session} onSignOut={signOut} />
      </Router>
    );
  }

  const landingPersona = session ? {
    persona_id: session.user.user_id,
    display_name: session.user.display_name,
    role: session.user.role,
    assigned_case_count: session.user.assigned_case_count,
    institution_id: session.user.institution_id,
  } : demoPersona;

  return (
    <LandingPage
      demoEnabled={Boolean(session || authStatus?.demo_auth_enabled)}
      demoPersona={landingPersona}
      starting={starting}
      error={error}
      onEnterDemo={enterWorkspace}
    />
  );
};

export const App: React.FC = () => <AuthGate />;
export default App;
