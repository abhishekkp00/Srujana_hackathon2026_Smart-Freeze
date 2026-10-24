import React, { useState, useEffect } from 'react';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Lock,
  KeyRound,
  FileKey,
  AlertTriangle,
  RefreshCw,
  Terminal,
  Filter,
  CheckCircle2,
  XCircle,
  Eye,
  Activity,
  Layers,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { StatCard } from '../components/common/StatCard';

interface SecurityStatus {
  status: string;
  auth_mode: string;
  production_auth_ready: boolean;
  demo_auth_enabled: boolean;
  pki_signature_algorithm: string;
  model_sha256_verified: boolean;
  bola_enforcement_active: boolean;
  rate_limiting_active: boolean;
  rate_limiting_scope: string;
  hidden_data_isolated: boolean;
  hidden_data_isolation_status: string;
  total_audit_events: number;
  security_denials_count: number;
  active_institutions_registered: number;
}

interface SecurityAuditEvent {
  event_id: string;
  timestamp: string;
  event_type: string;
  user_id?: string;
  user_role?: string;
  ip_address?: string;
  endpoint: string;
  method: string;
  details: Record<string, any>;
  severity: 'INFO' | 'WARNING' | 'HIGH' | 'CRITICAL';
}

export const SecurityAudit: React.FC = () => {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [events, setEvents] = useState<SecurityAuditEvent[]>([]);
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');
  const [actionFeedback, setActionFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const fetchSecurityData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, auditRes, casesRes] = await Promise.all([
        apiClient.get('/api/admin/security-status'),
        apiClient.get('/api/admin/audit-logs?limit=50'),
        apiClient.get('/api/cases'),
      ]);
      setStatus(statusRes.data);
      setEvents(auditRes.data);
      setCaseIds((casesRes.data || []).map((item: { case_id: string }) => item.case_id));
    } catch (err: any) {
      setError(err.message || 'Failed to load security audit telemetry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSecurityData();

    const handleAuthChange = () => {
      fetchSecurityData();
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => window.removeEventListener('auth-changed', handleAuthChange);
  }, []);

  // Quick adversarial test simulation triggers
  const triggerProbe = async (endpoint: string, label: string) => {
    setActionFeedback(null);
    try {
      await apiClient.get(endpoint);
      setActionFeedback({
        type: 'success',
        message: `${label}: HTTP ${200}. The endpoint responded; this alone does not prove the whole security control is effective.`,
      });
      fetchSecurityData();
    } catch (err: any) {
      setActionFeedback({
        type: 'error',
        message: `${label}: HTTP ${err?.response?.status ?? 'unavailable'} — ${err.message}. Review the response; a denial alone does not prove all access paths are protected.`,
      });
      fetchSecurityData();
    }
  };

  const filteredEvents = events.filter((e) => {
    if (selectedSeverity === 'ALL') return true;
    return e.severity === selectedSeverity;
  });

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 rounded-xl p-6 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-8 -translate-y-8 w-64 h-64 bg-teal-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div>
            <div className="flex items-center space-x-2 text-teal-400 text-xs font-semibold uppercase tracking-wider mb-2">
              <ShieldCheck className="w-4 h-4" />
              <span>Runtime configuration and audit evidence</span>
            </div>
            <h1 className="text-2xl font-extrabold text-white tracking-tight">
              Security posture and audit events
            </h1>
            <p className="text-slate-300 text-sm mt-1 max-w-3xl leading-relaxed">
              Shows the controls configured in this running instance. Local personas are simulated; OIDC production authentication is not implemented, and rate limiting is applied only to selected routes.
            </p>
          </div>
          <button
            onClick={fetchSecurityData}
            disabled={loading}
            className="flex items-center space-x-2 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg font-medium text-xs shadow-md transition-colors disabled:opacity-50 self-start md:self-auto"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Telemetry</span>
          </button>
        </div>
      </div>

      {/* Action Probe Feedback Banner */}
      {actionFeedback && (
        <div
          className={`p-4 rounded-xl border flex items-start space-x-3 text-sm transition-all duration-300 ${
            actionFeedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
              : 'bg-rose-50 border-rose-300 text-rose-900'
          }`}
        >
          {actionFeedback.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1">
            <span className="font-bold">{actionFeedback.type === 'success' ? 'Authorized Access' : 'Security Defense Activated'}: </span>
            <span>{actionFeedback.message}</span>
          </div>
        </div>
      )}

      {/* Role / Access Control Warning if error loading */}
      {error && (
        <div className="p-4 rounded-xl border border-amber-300 bg-amber-50 text-amber-900 flex items-start space-x-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-bold text-sm">Security telemetry unavailable</div>
            <div className="text-xs text-amber-800 mt-1">
              {error} The telemetry endpoint may require a local demo Compliance Admin session. The interface does not assume or silently select an administrator.
            </div>
          </div>
        </div>
      )}

      {/* Telemetry Stats */}
      {status && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Security Posture"
            value={status.status}
            subtext={status.production_auth_ready ? 'Production identity configured' : 'Production authentication is not configured'}
            icon={ShieldCheck}
            badge={{ text: status.auth_mode, variant: 'neutral' }}
          />
          <StatCard
            label="PKI & Signing Rail"
            value={status.pki_signature_algorithm.split(' ')[0]}
            subtext="Ed25519 + SHA-256 canonical"
            icon={KeyRound}
            badge={{ text: `${status.active_institutions_registered} Institutions`, variant: 'info' }}
          />
          <StatCard
            label="Model Hash Verified"
            value={status.model_sha256_verified ? 'VERIFIED' : 'UNVERIFIED'}
            subtext="True only when the loaded model artifact matches its recorded SHA-256 digest"
            icon={FileKey}
            badge={{ text: status.model_sha256_verified ? 'Digest matched' : 'No verified model digest', variant: status.model_sha256_verified ? 'success' : 'warning' }}
          />
          <StatCard
            label="Security Interceptions"
            value={status.security_denials_count}
            subtext={`${status.total_audit_events} total logged events`}
            icon={ShieldAlert}
            badge={{ text: status.total_audit_events > 0 ? 'Events recorded' : 'No events recorded', variant: 'neutral' }}
          />
        </div>
      )}

      {/* Threat Model & Active Defense Controls */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-800 flex items-center space-x-2 mb-4">
          <Layers className="w-5 h-5 text-indigo-600" />
          <span>Explicit Threat Model & Defensive Control Matrix</span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="flex items-center space-x-2 text-indigo-700 font-bold text-xs uppercase mb-1">
              <Lock className="w-4 h-4" />
              <span>BOLA & Horizontal Access</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              Every case-scoped request (Case Detail, Cytoscape Graph, Consensus Lien, TraceProof) verifies user assignment.
              Investigators cannot view or trace unassigned cases.
            </p>
          </div>

          <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="flex items-center space-x-2 text-teal-700 font-bold text-xs uppercase mb-1">
              <KeyRound className="w-4 h-4" />
              <span>Cryptographic Proof Integrity</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              The simulated evidence flow uses signed envelopes. Inspect individual verification results; cryptographic signatures do not establish that source records are factually correct.
            </p>
          </div>

          <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="flex items-center space-x-2 text-rose-700 font-bold text-xs uppercase mb-1">
              <ShieldAlert className="w-4 h-4" />
              <span>Model & Infrastructure Defense</span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              The configured model loader checks the artifact digest before deserialization. Request-size middleware and route-level rate limits are present; this is not a substitute for a security assessment.
            </p>
          </div>
        </div>

        {/* Live Adversarial Verification Buttons */}
        <div className="mt-6 pt-5 border-t border-slate-100">
          <div className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-slate-500" />
            <span>Interactive Adversarial Probes (Test Active Persona Defense)</span>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {caseIds[0] && <button
              onClick={() => triggerProbe('/api/cases/' + encodeURIComponent(caseIds[0]), 'Read case ' + caseIds[0])}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg border border-slate-300 transition-colors"
            >
              Probe: Read {caseIds[0]}
            </button>}
            {caseIds[1] && <button
              onClick={() => triggerProbe('/api/cases/' + encodeURIComponent(caseIds[1]), 'Read case ' + caseIds[1])}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg border border-slate-300 transition-colors"
            >
              Probe: Read {caseIds[1]}
            </button>}
            <button
              onClick={() => triggerProbe('/api/admin/audit-logs', 'Access Admin Audit Logs')}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg border border-slate-300 transition-colors"
            >
              Probe: Request Admin Audit Logs
            </button>
            <button
              onClick={() => triggerProbe('/api/admin/security-status', 'Access Admin Security Status')}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg border border-slate-300 transition-colors"
            >
              Probe: Request Security Status
            </button>
          </div>
        </div>
      </div>

      {/* Security Audit Log Table */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-base font-bold text-slate-800 flex items-center space-x-2">
              <Activity className="w-5 h-5 text-teal-600" />
              <span>Real-time Security Audit Log</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Recorded application events. Logs are application telemetry and have not been independently certified as immutable.
            </p>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="text-xs font-semibold bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical Only</option>
              <option value="HIGH">High Only</option>
              <option value="WARNING">Warning Only</option>
              <option value="INFO">Info Only</option>
            </select>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="overflow-x-auto border border-slate-100 rounded-lg">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="py-2.5 px-3">Event ID</th>
                <th className="py-2.5 px-3">Timestamp (UTC)</th>
                <th className="py-2.5 px-3">Severity</th>
                <th className="py-2.5 px-3">Event Type</th>
                <th className="py-2.5 px-3">User & Role</th>
                <th className="py-2.5 px-3">Endpoint</th>
                <th className="py-2.5 px-3">Sanitized Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400 font-sans">
                    No audit events found for selected severity level.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((evt) => {
                  let sevColor = 'bg-slate-100 text-slate-700 border-slate-200';
                  if (evt.severity === 'CRITICAL') sevColor = 'bg-rose-100 text-rose-800 border-rose-300 font-bold';
                  else if (evt.severity === 'HIGH') sevColor = 'bg-amber-100 text-amber-800 border-amber-300 font-bold';
                  else if (evt.severity === 'WARNING') sevColor = 'bg-yellow-100 text-yellow-800 border-yellow-300';
                  else if (evt.severity === 'INFO') sevColor = 'bg-blue-50 text-blue-700 border-blue-200';

                  return (
                    <tr key={evt.event_id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-2.5 px-3 font-semibold text-slate-800">{evt.event_id}</td>
                      <td className="py-2.5 px-3 text-slate-500 font-sans whitespace-nowrap">
                        {evt.timestamp.replace('T', ' ').substring(0, 19)}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] border ${sevColor}`}>
                          {evt.severity}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-indigo-700">{evt.event_type}</td>
                      <td className="py-2.5 px-3 font-sans">
                        {evt.user_id ? (
                          <div>
                            <span className="font-semibold text-slate-800">{evt.user_id}</span>{' '}
                            <span className="text-[10px] text-slate-400">({evt.user_role})</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">Unauthenticated</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">
                        <span className="text-[10px] px-1 py-0.5 bg-slate-200 rounded mr-1 font-bold">
                          {evt.method}
                        </span>
                        {evt.endpoint}
                      </td>
                      <td className="py-2.5 px-3 text-[11px] text-slate-600 max-w-xs truncate" title={JSON.stringify(evt.details)}>
                        {JSON.stringify(evt.details)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
