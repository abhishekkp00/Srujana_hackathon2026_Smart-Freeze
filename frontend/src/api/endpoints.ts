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
} from '../types';

export const getOverview = async (): Promise<OverviewData> => {
  const { data } = await apiClient.get<OverviewData>('/api/overview');
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

export const getAccounts = async (): Promise<AccountItem[]> => {
  const { data } = await apiClient.get<AccountItem[]>('/api/accounts');
  return data;
};

export const getAccountBalanceHistory = async (accountId: string): Promise<BalanceEventItem[]> => {
  const { data } = await apiClient.get<BalanceEventItem[]>(`/api/accounts/${accountId}/balance-history`);
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
