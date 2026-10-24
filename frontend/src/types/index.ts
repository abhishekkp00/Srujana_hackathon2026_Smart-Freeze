/**
 * Canonical TypeScript interfaces for Smart-Freeze Frontend.
 */

export interface OverviewData {
  accounts_analyzed: number;
  transactions_processed: number;
  cases_available: number;
  ledger_valid: boolean;
  validation_status: string;
  incomplete_history_accounts: number;
  cases_requiring_review: number;
  total_volume_inr: number;
  system_version: string;
  governance_disclaimer: string;
}

export interface CaseSummary {
  case_id: string;
  reported_date: string;
  reported_amount_paise: number;
  reported_amount_inr: number;
  status: string;
  transaction_count: number;
  origin_transaction_id?: string;
  priority_score?: number | null;
  priority_band: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNSCORED';
}

export interface TransactionItem {
  transaction_id: string;
  timestamp: string;
  from_account: string;
  to_account: string;
  amount_paise: number;
  amount_inr: number;
  transaction_type: string;
  case_id?: string | null;
  evidence_status: string;
}

export interface PaginatedTransactions {
  total: number;
  offset: number;
  limit: number;
  items: TransactionItem[];
}

export interface AccountItem {
  account_id: string;
  account_type: string;
  opening_balance_paise: number;
  opening_balance_inr: number;
  final_balance_paise: number;
  final_balance_inr: number;
  history_complete: boolean;
  is_external: boolean;
}

export interface BalanceEventItem {
  account_id: string;
  timestamp: string;
  transaction_id: string;
  counterparty_account: string;
  balance_before_paise: number;
  balance_before_inr: number;
  amount_change_paise: number;
  amount_change_inr: number;
  balance_after_paise: number;
  balance_after_inr: number;
  direction: 'CREDIT' | 'DEBIT';
  transaction_type: string;
  case_id: string;
  evidence_status: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  is_external: boolean;
  opening_balance_inr: number;
  final_balance_inr: number;
  history_complete: boolean;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  amount_paise: number;
  amount_inr: number;
  timestamp: string;
  transaction_type: string;
  case_id: string;
  evidence_status: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface AccountLienItem {
  account_id: string;
  proportional_paise: number;
  proportional_inr: number;
  fifo_paise: number;
  fifo_inr: number;
  libr_paise: number;
  libr_inr: number;
  lower_bound_paise: number;
  lower_bound_inr: number;
  upper_bound_paise: number;
  upper_bound_inr: number;
  disagreement_paise: number;
  disagreement_inr: number;
  is_external: boolean;
  history_complete: boolean;
}

export interface ConsensusLienData {
  case_id: string;
  source_transaction_id: string;
  source_amount_paise: number;
  source_amount_inr: number;
  consensus_status: string;
  total_lower_bound_paise: number;
  total_lower_bound_inr: number;
  total_upper_bound_paise: number;
  total_upper_bound_inr: number;
  total_disagreement_paise: number;
  total_disagreement_inr: number;
  account_liens: AccountLienItem[];
  method_details: {
    proportional: { status: string; assumption: string };
    fifo: { status: string; assumption: string };
    libr: { status: string; assumption: string };
  };
  explanation: {
    summary: string;
    account_explanations: Record<string, string>;
    assumptions: string[];
  };
  governance_notice: string;
}

export interface ComponentScoreData {
  component_name: string;
  score: number | null;
  weight: number;
  is_available: boolean;
  description: string;
  subfactors: Record<string, number>;
}

export interface PriorityScoreData {
  case_id: string;
  final_score: number | null;
  priority_band: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNSCORED';
  status: string;
  evidence_coverage: number;
  reported_amount_paise: number;
  reported_amount_inr: number;
  reported_date: string;
  component_b: ComponentScoreData;
  component_t: ComponentScoreData;
  component_h: ComponentScoreData;
  missing_components: string[];
  positive_factors: string[];
  mitigating_factors: string[];
  data_quality_warnings: string[];
  supporting_transaction_ids: string[];
  supporting_account_ids: string[];
  disclaimer: string;
}

export interface DataQualityDatasetItem {
  dataset_name: string;
  category: string;
  status: string;
  file_count: number;
  total_rows: number;
  columns_valid: boolean;
  warnings: string[];
  notes: string;
}

export interface DataQualityData {
  datasets: DataQualityDatasetItem[];
  overall_status: string;
  ledger_conservation_valid: boolean;
}

export interface MLStatusData {
  status: string;
  model_version?: string;
  algorithm?: string;
  selected_threshold?: number;
  feature_count: number;
  features: string[];
  training_timestamp?: string;
  dataset_source?: string;
  held_out_test_f1?: number;
  held_out_test_pr_auc?: number;
}

export interface ConfusionMatrixData {
  true_negatives: number;
  false_positives: number;
  false_negatives: number;
  true_positives: number;
}

export interface ModelMetricsData {
  model_name: string;
  precision: number;
  recall: number;
  f1_score: number;
  pr_auc: number;
  roc_auc: number;
  accuracy: number;
  confusion_matrix: ConfusionMatrixData;
  threshold_used: number;
  threshold_selection_reason: string;
}

export interface MLEvaluationReport {
  dataset_source: string;
  dataset_rows: number;
  fraud_count: number;
  non_fraud_count: number;
  train_size: number;
  val_size: number;
  test_size: number;
  features: string[];
  training_timestamp: string;
  random_seed: number;
  selected_model: string;
  selected_threshold: number;
  primary_model_metrics: ModelMetricsData;
  baseline_model_metrics: ModelMetricsData;
  governance_notice: string;
}

export interface MLDemoSample {
  sample_id: string;
  description: string;
  ground_truth_class: number;
  ground_truth_label: string;
  features: Record<string, number>;
}

export interface MLPredictResponse {
  predicted_class: number;
  predicted_label: string;
  model_score: number;
  threshold_used: number;
  model_version: string;
  algorithm: string;
  score_type: string;
  explanation: string;
  governance_notice: string;
}
