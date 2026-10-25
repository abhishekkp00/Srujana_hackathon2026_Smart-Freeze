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
  Link2,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { verifyAuditChain } from '../api/endpoints';
import { StatCard } from '../components/common/StatCard';
import { ChainVerificationData } from '../types';

interface SecurityStatus {
  status: string;
  auth_mode: string;
  production_auth_ready: boolean;
  demo_auth_enabled: boolean;
  pki_signature_algorithm: string;
  model_sha256_verified: boolean;
  case_scope_authorization_status: string;
  rate_limiting_active: boolean;
  rate_limiting_scope: string;
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
  previous_hash?: string;
  entry_hash?: string;
}

export const SecurityAudit: React.FC = () => {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [events, setEvents] = useState<SecurityAuditEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');

  // Audit Hash Chain Verification State
  const [verifyingChain, setVerifyingChain] = useState<boolean>(false);
  const [verificationResult, setVerificationResult] = useState<ChainVerificationData | null>(null);

  const fetchSecurityData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, auditRes] = await Promise.all([
        apiClient.get('/api/admin/security-status'),
        apiClient.get('/api/admin/audit-logs?limit=50'),
      ]);
      setStatus(statusRes.data);
      setEvents(auditRes.data);
    } catch (err: any) {
      setError(err.message || 'Failed to load security audit telemetry.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyChain = async () => {
    setVerifyingChain(true);
    try {
      const res = await verifyAuditChain();
      setVerificationResult(res);
    } catch (err: any) {
      setVerificationResult({
        is_valid: false,
        total_events: events.length,
        verified_events: 0,
        latest_hash: 'UNVERIFIED',
        error_message: err.response?.data?.detail || err.message || 'Chain verification failed.',
        governance_notice:
          'Cryptographic hash chaining proves algorithmic reproducibility and log integrity; it does not establish that logged actions reflect real-world truth.',
      });
    } finally {
      setVerifyingChain(false);
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
              Shows the controls configured in this running instance. Every audit entry is cryptographically SHA-256 hash-chained to the previous entry, establishing tamper-evident log provenance.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start md:self-auto">
            <button
              onClick={handleVerifyChain}
              disabled={verifyingChain}
              className="flex items-center space-x-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium text-xs shadow-md transition-colors disabled:opacity-50"
            >
              <Link2 className={`w-3.5 h-3.5 ${verifyingChain ? 'animate-spin' : ''}`} />
              <span>{verifyingChain ? 'Verifying...' : 'Verify Hash Chain'}</span>
            </button>
            <button
              onClick={fetchSecurityData}
              disabled={loading}
              className="flex items-center space-x-2 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg font-medium text-xs shadow-md transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh Telemetry</span>
            </button>
          </div>
        </div>
      </div>

      {/* Hash Chain Verification Result Banner */}
      {verificationResult && (
        <div
          className={`p-5 rounded-xl border shadow-sm transition-all ${
            verificationResult.is_valid
              ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950'
              : 'bg-rose-50/90 border-rose-300 text-rose-950'
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start space-x-3">
              {verificationResult.is_valid ? (
                <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-6 h-6 text-rose-600 flex-shrink-0 mt-0.5" />
              )}
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-sm tracking-tight">
                    {verificationResult.is_valid
                      ? 'Audit Hash Chain Verified Intact'
                      : 'Audit Hash Chain Integrity Violation Detected'}
                  </h3>
                  <span
                    className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                      verificationResult.is_valid
                        ? 'bg-emerald-200 text-emerald-800'
                        : 'bg-rose-200 text-rose-800'
                    }`}
                  >
                    {verificationResult.is_valid ? 'UNBROKEN CHAIN' : 'TAMPER DETECTED'}
                  </span>
                </div>
                <p className="text-xs mt-1 text-slate-700">
                  {verificationResult.is_valid ? (
                    <>
                      Verified <span className="font-semibold">{verificationResult.verified_events}</span> of{' '}
                      <span className="font-semibold">{verificationResult.total_events}</span> events from genesis.
                      Latest block digest:{' '}
                      <code className="font-mono bg-white/70 px-1.5 py-0.5 rounded border border-emerald-200 text-[11px]">
                        {verificationResult.latest_hash}
                      </code>
                    </>
                  ) : (
                    <>
                      {verificationResult.error_message}{' '}
                      {verificationResult.tampered_event_id && (
                        <span className="font-semibold underline">
                          Tampered Event: {verificationResult.tampered_event_id}
                        </span>
                      )}
                    </>
                  )}
                </p>
                <div className="mt-2 text-[11px] italic text-slate-600 border-t border-slate-200/60 pt-1.5">
                  <strong>Notice on Limitation:</strong> {verificationResult.governance_notice}
                </div>
              </div>
            </div>
            <button
              onClick={() => setVerificationResult(null)}
              className="text-xs text-slate-400 hover:text-slate-600 font-semibold px-2 py-1"
            >
              Dismiss
            </button>
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
            label="PKI & Proofs"
            value="Ed25519"
            subtext={status.pki_signature_algorithm}
            icon={KeyRound}
            badge={{ text: 'Signed Envelopes & Receipts', variant: 'info' }}
          />
          <StatCard
            label="Rate Limiting"
            value={status.rate_limiting_active ? 'Active' : 'Disabled'}
            subtext={status.rate_limiting_scope}
            icon={Lock}
            badge={{ text: status.rate_limiting_active ? 'Route-Level Scope' : 'Disabled', variant: status.rate_limiting_active ? 'success' : 'warning' }}
          />
          <StatCard
            label="Audit Trail"
            value={`${status.total_audit_events} Events`}
            subtext="SHA-256 Hash Chained"
            icon={Activity}
            badge={{ text: 'Tamper Evident', variant: 'success' }}
          />
        </div>
      )}

      {/* Controls Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex items-center space-x-2 text-indigo-700 font-bold text-xs uppercase mb-1">
            <Lock className="w-4 h-4" />
            <span>Role-Based Access Control</span>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            API endpoints enforce investigator and compliance roles in FastAPI. Case-scoped object-level authorization (BOLA prevention) is enforced before processing.
          </p>
        </div>

        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex items-center space-x-2 text-teal-700 font-bold text-xs uppercase mb-1">
            <KeyRound className="w-4 h-4" />
            <span>Cryptographic Proof Integrity</span>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            Evidence flow uses signed Ed25519 envelopes and hold receipts. Inspect individual verification results; cryptographic signatures do not establish that source records are factually correct.
          </p>
        </div>

        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <div className="flex items-center space-x-2 text-rose-700 font-bold text-xs uppercase mb-1">
            <ShieldAlert className="w-4 h-4" />
            <span>Model & Infrastructure Defense</span>
          </div>
          <p className="text-xs text-slate-600 leading-relaxed">
            The model loader checks a configured artifact digest before deserialization. Request-size middleware is installed; rate limits cover selected routes only.
          </p>
        </div>
      </div>

      {/* Security Audit Log Table */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div>
            <h2 className="text-base font-bold text-slate-800 flex items-center space-x-2">
              <Activity className="w-5 h-5 text-teal-600" />
              <span>Recorded security events (Hash-Chained)</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Every audit record includes the cryptographic SHA-256 hash of its predecessor, creating a verifiable chronological hash chain.
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
                <th className="py-2.5 px-3">Hash Link (Prev → Current)</th>
                <th className="py-2.5 px-3">User & Role</th>
                <th className="py-2.5 px-3">Endpoint</th>
                <th className="py-2.5 px-3">Sanitized Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400 font-sans">
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

                  const prevShort = evt.previous_hash ? evt.previous_hash.substring(0, 8) : '00000000';
                  const currShort = evt.entry_hash ? evt.entry_hash.substring(0, 8) : '--------';

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
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500" title={`Prev: ${evt.previous_hash}\nCurrent: ${evt.entry_hash}`}>
                        <span className="text-slate-400">{prevShort}</span>
                        <span className="text-slate-300 mx-1">→</span>
                        <span className="text-indigo-600 font-bold">{currShort}</span>
                      </td>
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
