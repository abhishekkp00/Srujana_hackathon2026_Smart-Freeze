import { apiClient } from './client';
import {
  OverviewData,
  CaseSummary,
  PaginatedTransactions,
  AccountItem,
  BalanceEventItem,
  GraphData,
  ConsensusLienData,
  PriorityScoreData,
  DataQualityData,
  MLStatusData,
  MLEvaluationReport,
  MLDemoSample,
  MLPredictResponse,
  TraceProofScenario,
  SignedEvidenceEnvelope,
  EnvelopeVerificationResult,
  TraceProofResponse,
  StartTraceRequest,
  HoldPreview,
  DemoHoldProposal,
  DemoHoldProposalRequest,
  CaseRecommendationsData,
  AccountRecommendation,
  AttackLabReportData,
  ChainVerificationData,
  ReceiptData,
} from '../types';

export const getOverview = async (params?: { start_date?: string; end_date?: string }): Promise<OverviewData> => {
  const { data } = await apiClient.get<OverviewData>('/api/overview', { params });
  return data;
};

export const getCases = async (): Promise<CaseSummary[]> => {
  const { data } = await apiClient.get<CaseSummary[]>('/api/cases');
  return data;
};

export const getCaseDetail = async (caseId: string): Promise<any> => {
  const { data } = await apiClient.get(`/api/cases/${caseId}`);
  return data;
};

export const getTransactions = async (params?: {
  case_id?: string;
  account_id?: string;
  transaction_type?: string;
  evidence_status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedTransactions> => {
  const { data } = await apiClient.get<PaginatedTransactions>('/api/transactions', { params });
  return data;
};

export const getTransactionDetail = async (txId: string): Promise<any> => {
  const { data } = await apiClient.get(`/api/transactions/${txId}`);
  return data;
};

export const getAccounts = async (caseId?: string): Promise<AccountItem[]> => {
  const { data } = await apiClient.get<AccountItem[]>('/api/accounts', {
    params: caseId ? { case_id: caseId } : {},
  });
  return data;
};

export const getAccountBalanceHistory = async (accountId: string, caseId?: string): Promise<BalanceEventItem[]> => {
  const { data } = await apiClient.get<BalanceEventItem[]>(`/api/accounts/${encodeURIComponent(accountId)}/balance-history`, {
    params: caseId ? { case_id: caseId } : {},
  });
  return data;
};

export const getGraphData = async (caseId?: string): Promise<GraphData> => {
  const { data } = await apiClient.get<GraphData>('/api/graph', {
    params: caseId ? { case_id: caseId } : undefined,
  });
  return data;
};

export const getConsensusLien = async (caseId: string): Promise<ConsensusLienData> => {
  const { data } = await apiClient.get<ConsensusLienData>(`/api/consensus-lien/${caseId}`);
  return data;
};

export const getHoldPreview = async (caseId: string): Promise<HoldPreview> => {
  const { data } = await apiClient.get<HoldPreview>(`/api/hold-preview/${encodeURIComponent(caseId)}`);
  return data;
};

export const createDemoHoldProposal = async (request: DemoHoldProposalRequest): Promise<DemoHoldProposal> => {
  const { data } = await apiClient.post<DemoHoldProposal>('/api/hold-proposals', request);
  return data;
};

export const getDemoHoldProposals = async (caseId: string): Promise<DemoHoldProposal[]> => {
  const { data } = await apiClient.get<DemoHoldProposal[]>('/api/hold-proposals', { params: { case_id: caseId } });
  return data;
};

export const getInvestigationPriorityScores = async (): Promise<PriorityScoreData[]> => {
  const { data } = await apiClient.get<PriorityScoreData[]>('/api/investigation-priority');
  return data;
};

export const getCasePriorityScore = async (caseId: string): Promise<PriorityScoreData> => {
  const { data } = await apiClient.get<PriorityScoreData>(`/api/investigation-priority/${caseId}`);
  return data;
};

export const getDataQuality = async (): Promise<DataQualityData> => {
  const { data } = await apiClient.get<DataQualityData>('/api/data-quality');
  return data;
};

// ==============================================================================
// ML Fraud Classifier Endpoints
// ==============================================================================

export const getMLStatus = async (): Promise<MLStatusData> => {
  const { data } = await apiClient.get<MLStatusData>('/api/ml/status');
  return data;
};

export const getMLEvaluation = async (): Promise<MLEvaluationReport> => {
  const { data } = await apiClient.get<MLEvaluationReport>('/api/ml/evaluation');
  return data;
};

export const getMLDemoSamples = async (): Promise<MLDemoSample[]> => {
  const { data } = await apiClient.get<MLDemoSample[]>('/api/ml/demo-samples');
  return data;
};

export const predictFraud = async (features: Record<string, number>): Promise<MLPredictResponse> => {
  const { data } = await apiClient.post<MLPredictResponse>('/api/ml/predict', { features });
  return data;
};

// ==============================================================================
// TraceProof Multi-Rail Evidence Reconstruction Endpoints
// ==============================================================================

export const getTraceProofScenarios = async (): Promise<TraceProofScenario[]> => {
  const { data } = await apiClient.get<TraceProofScenario[]>('/api/traceproof/scenarios');
  return data;
};

export const startTraceProof = async (req: StartTraceRequest): Promise<TraceProofResponse> => {
  const { data } = await apiClient.post<TraceProofResponse>('/api/traceproof/start', req);
  return data;
};

export const getTraceProofResult = async (requestId: string): Promise<TraceProofResponse> => {
  const { data } = await apiClient.get<TraceProofResponse>(`/api/traceproof/requests/${requestId}`);
  return data;
};

export const verifyEvidenceEnvelope = async (
  envelope: SignedEvidenceEnvelope
): Promise<EnvelopeVerificationResult> => {
  const { data } = await apiClient.post<EnvelopeVerificationResult>('/api/traceproof/verify-envelope', {
    envelope,
  });
  return data;
};

export const getCaseRecommendations = async (
  caseId: string,
  policy: string = 'balanced',
  deMinimisPaise?: number
): Promise<CaseRecommendationsData> => {
  const params: Record<string, any> = { policy };
  if (deMinimisPaise !== undefined) {
    params.de_minimis_paise = deMinimisPaise;
  }
  const { data } = await apiClient.get<CaseRecommendationsData>(`/api/cases/${caseId}/recommendations`, { params });
  return data;
};

export const getAttackLabReport = async (params?: {
  seed?: number;
  population?: number;
  generations?: number;
}): Promise<AttackLabReportData> => {
  const { data } = await apiClient.get<AttackLabReportData>('/api/attacklab/run', { params });
  return data;
};

export const verifyAuditChain = async (): Promise<ChainVerificationData> => {
  const { data } = await apiClient.post<ChainVerificationData>('/api/admin/audit/verify-chain');
  return data;
};

export const getReceipt = async (receiptId: string): Promise<ReceiptData> => {
  const { data } = await apiClient.get<ReceiptData>(`/api/receipts/${receiptId}`);
  return data;
};

export const getCaseReceipts = async (caseId: string): Promise<ReceiptData[]> => {
  const { data } = await apiClient.get<ReceiptData[]>(`/api/cases/${caseId}/receipts`);
  return data;
};


