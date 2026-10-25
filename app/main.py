"""Smart-Freeze FastAPI Backend Application.

Serves verified ledger analysis, multi-method fund tracing, Consensus Lien comparisons,
explainable investigation priority scoring, and data quality audits to the React frontend.
Strictly isolates hidden evaluation ground truth from operational APIs.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Tuple
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd

from engine.behavioural_features import CaseFeatures
from engine.consensus_explanations import ConsensusExplanationBuilder
from engine.consensus_lien import ConsensusLienEngine, ConsensusLienResult
from engine.decision import DecisionEngine, DecisionAction, CaseRecommendationsResult
from engine.fifo import FIFOTracer
from engine.investigation_score import (
    GOVERNANCE_DISCLAIMER,
    CasePriorityScore,
    InvestigationScoringEngine,
    ScoringConfig,
)
from engine.ledger import LedgerReconstructionEngine
from engine.libr import LIBRTracer
from engine.proportional import ProportionalTracer
from engine.transaction_graph import TransactionGraphEngine
from pipeline.adapters.synthetic_adapter import SyntheticAdapter
from pipeline.profiling import DatasetProfile
from pipeline.schemas import (EXTERNAL_ACCOUNT_PREFIX, DatasetType, CANONICAL_ACCOUNT_COLUMNS, CANONICAL_TRANSACTION_COLUMNS, CANONICAL_CASE_COLUMNS, ELLIPTIC_CLASSES_COLUMNS, ELLIPTIC_EDGELIST_COLUMNS, AMLNET_COLUMNS, SYNTHAML_ALERTS_COLUMNS)
from ml.service import MLService, ModelArtifactError
from ml.schemas import PredictRequest, PredictResponse, FEATURE_NAMES, TARGET_NAME
from traceproof.coordinator import TraceCoordinator
from traceproof.crypto import InstitutionKeyManager
from traceproof.scenarios import get_scenario_metadata_list
from traceproof.schemas import (
    StartTraceRequest,
    TraceProofResponse,
    VerifyEnvelopeRequest,
    EnvelopeVerificationResult,
)
from federated.coordinator import FederatedCoordinator
from federated.schemas import FederatedComparisonResponse
from security.models import (
    Role,
    AuthContext,
    SecurityAuditEvent,
    SecurityStatusResponse,
    AuditSeverity,
    User,
    ChainVerificationResponse,
)
from security.receipt import ReceiptRegistry, create_hold_receipt
from security.auth import (
    get_current_user,
    require_role,
    check_case_access,
    DEMO_PERSONAS,
    DEMO_AUTH_ENABLED,
    ENV_MODE,
    issue_demo_token,
)
from security.audit import SecurityAuditLogger
from security.rate_limiter import rate_limit
from security.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent
SYNTHETIC_DIR = ROOT_DIR / "data" / "synthetic"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
RAW_DIR = ROOT_DIR / "data" / "raw"

# Initialize FastAPI app
app = FastAPI(
    title="Smart-Freeze API",
    description="Transparent Fraud Investigation and Fund-Tracing Decision-Support API",
    version="1.0.0",
)

# Enforce Request Size Limit Middleware (1MB max payload)
app.add_middleware(RequestSizeLimitMiddleware)

# Enforce Defense-in-Depth HTTP Security Headers (CSP, HSTS, XFO, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Configure CORS with strict explicit origins
origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000")
allowed_origins = [o.strip() for o in origins_str.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Sanitized global exception handler preventing information disclosure.
    
    Logs full stack trace and details internally with a unique incident UUID,
    returning a safe error message without internal filesystem paths or stack traces.
    """
    if isinstance(exc, HTTPException):
        # Re-raise standard HTTP exceptions to preserve intended status codes
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    incident_id = f"INC_{uuid.uuid4().hex[:8].upper()}"
    client_ip = request.client.host if request.client else "unknown"
    audit = SecurityAuditLogger.get_instance()
    audit.log_event(
        event_type="UNHANDLED_EXCEPTION",
        endpoint=request.url.path,
        method=request.method,
        severity=AuditSeverity.CRITICAL,
        ip_address=client_ip,
        details={
            "incident_id": incident_id,
            "error_type": type(exc).__name__,
            "message": str(exc),
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Authorized administrators may reference the incident ID.",
            "incident_id": incident_id,
        },
    )

# Cached resources
_adapter: Optional[SyntheticAdapter] = None
_reconstructed_ledger: Optional[Dict[str, Any]] = None
_ledger_cache_signature: Optional[Tuple[Tuple[int, int], ...]] = None
_scoring_engine: Optional[InvestigationScoringEngine] = None
# Demo-only hold proposals live in process memory and are never sent to a bank.
DEMO_HOLD_PROPOSALS: List[Dict[str, Any]] = []


def get_adapter() -> SyntheticAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SyntheticAdapter(SYNTHETIC_DIR)
        if not _adapter.exists():
            raise HTTPException(
                status_code=503,
                detail="Required operational ledger CSV files are unavailable. Check the Data Quality page and local dataset setup.",
            )
    return _adapter


def get_ledger_data() -> Dict[str, Any]:
    """Load a validated ledger cache and rebuild it when any source CSV changes."""
    global _reconstructed_ledger, _ledger_cache_signature
    adapter = get_adapter()
    source_paths = (adapter.accounts_path, adapter.transactions_path, adapter.cases_path)
    try:
        signature = tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in source_paths)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="One or more operational ledger files are unavailable.") from exc

    if _reconstructed_ledger is not None and signature == _ledger_cache_signature:
        return _reconstructed_ledger

    accounts_df = pd.read_csv(adapter.accounts_path)
    transactions_df = pd.read_csv(adapter.transactions_path)
    cases_df = pd.read_csv(adapter.cases_path)

    engine = LedgerReconstructionEngine(SYNTHETIC_DIR)
    tracker, graph, report = engine.reconstruct(
        accounts_df=accounts_df,
        transactions_df=transactions_df,
    )
    balances = {aid: state.current_balance_paise for aid, state in tracker.accounts.items()}
    balance_events = tracker.balance_events
    graph_summary = TransactionGraphEngine.summarize_graph(graph)

    _reconstructed_ledger = {
        "accounts_df": accounts_df,
        "transactions_df": transactions_df,
        "cases_df": cases_df,
        "validation_report": report,
        "final_balances": balances,
        "balance_events": balance_events,
        "graph": graph,
        "graph_summary": graph_summary,
    }
    _ledger_cache_signature = signature
    return _reconstructed_ledger


def select_case_source_transaction(case_transactions: pd.DataFrame) -> Optional[pd.Series]:
    """Select one deterministic source transaction consistently across case, graph and tracing APIs."""
    if case_transactions.empty:
        return None
    ordered = case_transactions.copy()
    ordered["_source_sort_timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True, errors="coerce")
    ordered = ordered.sort_values(["_source_sort_timestamp", "transaction_id"], kind="stable")
    if "evidence_status" in ordered.columns:
        suspected = ordered[ordered["evidence_status"].astype(str).str.lower() == "suspected_fraud"]
    else:
        suspected = ordered.iloc[0:0]
    selected = suspected.iloc[0] if not suspected.empty else ordered.iloc[0]
    return selected.drop(labels=["_source_sort_timestamp"], errors="ignore")


def get_scoring_engine() -> InvestigationScoringEngine:
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = InvestigationScoringEngine(config=ScoringConfig())
    return _scoring_engine


_CSV_PROFILE_CACHE: Dict[Tuple[str, int, int, str, Tuple[str, ...], Optional[int], Optional[str]], Dict[str, Any]] = {}

def _profile_csv(path: Path, required_columns: Optional[List[str]] = None, header: Any = "infer", expected_column_count: Optional[int] = None, target_column: Optional[str] = None) -> Dict[str, Any]:
    """Profile a local CSV from its actual header and row stream; cache only until the file changes."""
    if not path.is_file():
        return {"exists": False, "parsed": False, "columns": [], "rows": 0, "columns_valid": False, "target_counts": {}, "error": None}
    stat = path.stat()
    required = tuple(required_columns or [])
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size, str(header), required, expected_column_count, target_column)
    if key in _CSV_PROFILE_CACHE:
        return _CSV_PROFILE_CACHE[key]
    profile: Dict[str, Any] = {"exists": True, "parsed": False, "columns": [], "rows": 0, "columns_valid": False, "target_counts": {}, "error": None}
    try:
        head = pd.read_csv(path, header=header, nrows=0)
        columns = [str(col) for col in head.columns.tolist()]
        profile["columns"] = columns
        profile["columns_valid"] = set(required).issubset(set(columns)) and (expected_column_count is None or len(columns) == expected_column_count)
        profile["parsed"] = True
        if len(head.columns):
            count_col = head.columns[0]
            profile["rows"] = sum(len(chunk) for chunk in pd.read_csv(path, header=header, usecols=[count_col], chunksize=100000))
        if target_column and target_column in columns:
            counts: Dict[str, int] = {}
            for chunk in pd.read_csv(path, usecols=[target_column], chunksize=100000):
                for value, count in chunk[target_column].astype(str).value_counts(dropna=False).items():
                    counts[str(value)] = counts.get(str(value), 0) + int(count)
            profile["target_counts"] = counts
    except Exception as exc:
        profile["error"] = type(exc).__name__
        profile["parsed"] = False
        profile["columns_valid"] = False
    if len(_CSV_PROFILE_CACHE) > 64:
        _CSV_PROFILE_CACHE.clear()
    _CSV_PROFILE_CACHE[key] = profile
    return profile

# ==============================================================================
# Pydantic Response Models
# ==============================================================================

class OverviewResponse(BaseModel):
    accounts_analyzed: int
    transactions_processed: int
    cases_available: int
    ledger_valid: bool
    validation_status: str
    incomplete_history_accounts: int
    cases_requiring_review: int
    total_volume_inr: float
    system_version: str
    governance_disclaimer: str


class CaseSummary(BaseModel):
    case_id: str
    reported_date: str
    reported_amount_paise: int
    reported_amount_inr: float
    status: str
    transaction_count: int
    origin_transaction_id: Optional[str] = None
    priority_score: Optional[float] = None
    priority_band: str = "UNSCORED"


class TransactionItem(BaseModel):
    transaction_id: str
    timestamp: str
    from_account: str
    to_account: str
    amount_paise: int
    amount_inr: float
    transaction_type: str
    case_id: Optional[str] = None
    evidence_status: str


class PaginatedTransactions(BaseModel):
    total: int
    offset: int
    limit: int
    items: List[TransactionItem]


class AccountItem(BaseModel):
    account_id: str
    account_type: str
    opening_balance_paise: int
    opening_balance_inr: float
    final_balance_paise: int
    final_balance_inr: float
    history_complete: bool
    is_external: bool


class BalanceEventItem(BaseModel):
    account_id: str
    timestamp: str
    transaction_id: str
    counterparty_account: str
    balance_before_paise: int
    balance_before_inr: float
    amount_change_paise: int
    amount_change_inr: float
    balance_after_paise: int
    balance_after_inr: float
    direction: str
    transaction_type: str
    case_id: str
    evidence_status: str


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    is_external: bool
    opening_balance_inr: Optional[float] = None
    final_balance_inr: Optional[float] = None
    history_complete: Optional[bool] = None
    flow_level: Optional[int] = None
    is_origin_account: bool = False
    flagged_by_case_evidence: bool = False


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    amount_paise: int
    amount_inr: float
    timestamp: str
    transaction_type: str
    case_id: str
    evidence_status: str
    flow_hop: Optional[int] = None
    linkage_basis: str = "LEDGER_RECORD"
    is_source_transaction: bool = False


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int
    source_transaction_id: Optional[str] = None
    source_amount_inr: Optional[float] = None
    flow_scope: Optional[str] = None


class AccountLienItem(BaseModel):
    account_id: str
    proportional_paise: int
    proportional_inr: float
    fifo_paise: int
    fifo_inr: float
    libr_paise: int
    libr_inr: float
    lower_bound_paise: int
    lower_bound_inr: float
    upper_bound_paise: int
    upper_bound_inr: float
    disagreement_paise: int
    disagreement_inr: float
    is_external: bool
    history_complete: bool


class ConsensusLienResponse(BaseModel):
    case_id: str
    source_transaction_id: str
    source_amount_paise: int
    source_amount_inr: float
    consensus_status: str
    total_lower_bound_paise: int
    total_lower_bound_inr: float
    total_upper_bound_paise: int
    total_upper_bound_inr: float
    total_disagreement_paise: int
    total_disagreement_inr: float
    joint_feasible_upper_paise: Optional[int] = None
    joint_feasible_upper_inr: Optional[float] = None
    confirmed_withdrawn_paise: Optional[int] = None
    confirmed_withdrawn_inr: Optional[float] = None
    unconstrained_upper_bound_paise: Optional[int] = None
    unconstrained_upper_bound_inr: Optional[float] = None
    account_liens: List[AccountLienItem]
    method_details: Dict[str, Any]
    explanation: Dict[str, Any]
    governance_notice: str


class HoldCandidateResponse(BaseModel):
    account_id: str
    account_type: str
    current_balance_paise: Optional[int] = None
    current_balance_inr: Optional[float] = None
    lower_bound_paise: int
    lower_bound_inr: float
    upper_bound_paise: int
    upper_bound_inr: float
    proposed_hold_paise: int
    proposed_hold_inr: float
    history_complete: Optional[bool] = None
    is_eligible: bool
    eligibility_reason: str
    linked_suspicious_transaction_ids: List[str]


class HoldPreviewResponse(BaseModel):
    case_id: str
    source_transaction_id: str
    source_amount_paise: int
    source_amount_inr: float
    consensus_status: str
    candidates: List[HoldCandidateResponse]
    formula: str
    execution_status: str
    disclaimer: str


class DemoHoldProposalRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=100)
    account_id: str = Field(..., min_length=1, max_length=150)


class DemoHoldProposalResponse(BaseModel):
    proposal_id: str
    audit_event_id: str
    created_at: str
    case_id: str
    source_transaction_id: str
    account_id: str
    current_balance_paise: int
    current_balance_inr: float
    consensus_lower_bound_paise: int
    consensus_lower_bound_inr: float
    proposed_hold_paise: int
    proposed_hold_inr: float
    calculation: str
    status: str
    execution_status: str
    message: str
    receipt_id: Optional[str] = None


class PriorityScoreResponse(BaseModel):
    case_id: str
    final_score: Optional[float]
    priority_band: str
    status: str
    evidence_coverage: float
    reported_amount_paise: int
    reported_amount_inr: float
    reported_date: str
    component_b: Dict[str, Any]
    component_t: Dict[str, Any]
    component_h: Dict[str, Any]
    missing_components: List[str]
    positive_factors: List[str]
    mitigating_factors: List[str]
    data_quality_warnings: List[str]
    supporting_transaction_ids: List[str]
    supporting_account_ids: List[str]
    disclaimer: str


class DataQualityDatasetItem(BaseModel):
    dataset_name: str
    category: str
    status: str
    file_count: int
    total_rows: int
    columns_valid: bool
    warnings: List[str]
    notes: str


class DataQualityResponse(BaseModel):
    datasets: List[DataQualityDatasetItem]
    overall_status: str
    ledger_conservation_valid: bool


class AccountRecommendationModel(BaseModel):
    account_id: str
    core: int
    margin: int
    free: int
    action: str
    reasons: List[str]
    policy_version: str
    requires_human_approval: bool
    harm_score: float = 0.0
    mule_score: float = 0.0
    current_balance_paise: int = 0
    held_core_paise: int = 0
    held_margin_paise: int = 0
    effective_lien_paise: int = 0
    margin_hold_duration_hours: Optional[int] = None
    receipt_id: Optional[str] = None


class CaseRecommendationsResponse(BaseModel):
    case_id: str
    policy_name: str
    policy_version: str
    stolen_amount_paise: int
    joint_cap_paise: int
    recommendations: List[AccountRecommendationModel]
    total_core_paise: int
    total_margin_paise: int
    total_held_paise: int
    requires_human_approval_count: int
    governance_notice: str


# ==============================================================================
# Authentication & Identity Endpoints
# ==============================================================================

@app.get("/api/auth/status")
def get_auth_status() -> Dict[str, Any]:
    """Report the configured identity mode without implying production OIDC is ready."""
    return {
        "env_mode": ENV_MODE,
        "demo_auth_enabled": DEMO_AUTH_ENABLED,
        "production_auth_ready": False,
        "auth_provider": "local-demo" if DEMO_AUTH_ENABLED else "unconfigured",
        "message": (
            "Local demonstration identities are enabled; they are not real bank identities."
            if DEMO_AUTH_ENABLED else
            "No fully implemented identity provider is configured. Protected APIs fail closed."
        ),
    }


def build_local_demo_user() -> User:
    """Create one clearly-labelled demo investigator whose access scope follows the loaded case file."""
    data = get_ledger_data()
    assigned_case_ids = sorted(data["cases_df"]["case_id"].astype(str).unique().tolist())
    return User(
        user_id="LOCAL_DEMO_INVESTIGATOR",
        email="demo-investigator@localhost.invalid",
        display_name="Local demo investigator",
        role=Role.INVESTIGATOR,
        assigned_cases=assigned_case_ids,
        institution_id="LOCAL_SYNTHETIC_LEDGER",
    )


@app.get("/api/auth/personas")
def get_auth_personas() -> Dict[str, Any]:
    """Expose one local demonstration identity, not a fabricated directory of bank employees."""
    if not DEMO_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Local demonstration identities are disabled.")
    user = build_local_demo_user()
    return {
        "mode": "LOCAL_DEMO_ONLY",
        "personas": [{
            "persona_id": user.user_id,
            "display_name": user.display_name,
            "role": user.role.value,
            "assigned_case_count": len(user.assigned_cases),
            "institution_id": user.institution_id,
        }],
    }


class DemoSessionRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=100)


@app.post("/api/auth/demo-session")
def create_demo_session(req: DemoSessionRequest) -> Dict[str, Any]:
    """Issue a short-lived token for the single local demo investigator."""
    if not DEMO_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Local demonstration identities are disabled.")
    user = build_local_demo_user()
    if req.persona_id != user.user_id:
        raise HTTPException(status_code=404, detail="Unknown demonstration identity.")
    token, expires_at = issue_demo_token(user)
    return {
        "mode": "LOCAL_DEMO_ONLY",
        "token": token,
        "expires_at": expires_at.isoformat(),
        "user": {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "role": user.role.value,
            "institution_id": user.institution_id,
        },
        "warning": "This short-lived identity is for isolated synthetic-data demos only.",
    }


@app.get("/api/auth/session")
def get_auth_session(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the current authenticated identity without returning credentials."""
    return {
        "mode": auth.token_type,
        "user": {
            "user_id": auth.user.user_id,
            "display_name": auth.user.display_name,
            "role": auth.user.role.value,
            "institution_id": auth.user.institution_id,
            "assigned_case_count": len(auth.user.assigned_cases),
        },
    }


# ==============================================================================
# Operational APIs
# ==============================================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint (public liveness probe)."""
    return {"status": "healthy", "service": "smart-freeze-api", "version": app.version}


@app.get("/api/overview", response_model=OverviewResponse)
def get_overview(auth: AuthContext = Depends(get_current_user)):
    """Returns top-level operational statistics and data health status."""
    data = get_ledger_data()
    all_accs = data["accounts_df"]
    all_txs = data["transactions_df"]
    all_cases = data["cases_df"]
    report = data["validation_report"]

    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        cases = all_cases[all_cases["case_id"].isin(auth.user.assigned_cases)]
        txs = all_txs[all_txs["case_id"].isin(auth.user.assigned_cases)]
        account_ids = set(txs["from_account"]).union(set(txs["to_account"]))
        accs = all_accs[all_accs["account_id"].isin(account_ids)]
    else:
        accs, txs, cases = all_accs, all_txs, all_cases

    incomplete_accs = int((~accs["history_complete"].astype(bool)).sum()) if "history_complete" in accs.columns else 0
    total_vol_paise = int(txs["amount_paise"].sum())
    closed_statuses = {"CLOSED", "RESOLVED", "COMPLETED", "DISMISSED"}
    cases_requiring_review = int((~cases["status"].astype(str).str.upper().isin(closed_statuses)).sum()) if not cases.empty else 0

    return OverviewResponse(
        accounts_analyzed=len(accs),
        transactions_processed=len(txs),
        cases_available=len(cases),
        ledger_valid=report.is_valid,
        validation_status="VERIFIED" if report.is_valid else "VALIDATION_FAILED",
        incomplete_history_accounts=incomplete_accs,
        cases_requiring_review=cases_requiring_review,
        total_volume_inr=total_vol_paise / 100.0,
        system_version=app.version,
        governance_disclaimer=GOVERNANCE_DISCLAIMER,
    )


@app.get("/api/cases", response_model=List[CaseSummary])
def list_cases(auth: AuthContext = Depends(get_current_user)):
    """Lists authorized cases with transaction counts, loss amounts, and priority scores."""
    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    # Filter cases based on user's authorized scope if Investigator
    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        cases_df = cases_df[cases_df["case_id"].isin(auth.user.assigned_cases)]

    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        txs_df = txs_df[txs_df["case_id"].isin(auth.user.assigned_cases)]
        involved_accounts = set(txs_df["from_account"]).union(set(txs_df["to_account"]))
        accs_df = accs_df[accs_df["account_id"].isin(involved_accounts)]

    engine = get_scoring_engine()
    scores = engine.score_all_cases(cases_df, txs_df, accs_df)
    score_map = {s.case_id: s for s in scores}

    result = []
    for _, row in cases_df.iterrows():
        cid = str(row["case_id"])
        rep_amt = int(row["reported_amount_paise"])
        case_txs = txs_df[txs_df["case_id"] == cid]
        source_row = select_case_source_transaction(case_txs)
        origin_tx = str(source_row["transaction_id"]) if source_row is not None else None

        sc = score_map.get(cid)
        result.append(
            CaseSummary(
                case_id=cid,
                reported_date=str(row["reported_date"]),
                reported_amount_paise=rep_amt,
                reported_amount_inr=rep_amt / 100.0,
                status=str(row["status"]),
                transaction_count=len(case_txs),
                origin_transaction_id=origin_tx,
                priority_score=sc.final_score if sc else None,
                priority_band=sc.priority_band if sc else "UNSCORED",
            )
        )
    return result


@app.get("/api/cases/{case_id}")
def get_case_detail(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
):
    """Returns detailed information for a specific case with BOLA verification."""
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)
    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    matched = cases_df[cases_df["case_id"] == case_id]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    row = matched.iloc[0]
    case_txs = txs_df[txs_df["case_id"] == case_id]
    source_row = select_case_source_transaction(case_txs)
    origin_tx = str(source_row["transaction_id"]) if source_row is not None else None

    scoring_txs = txs_df
    scoring_accounts = accs_df
    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        scoring_txs = txs_df[txs_df["case_id"].isin(auth.user.assigned_cases)]
        involved_accounts = set(scoring_txs["from_account"]).union(set(scoring_txs["to_account"]))
        scoring_accounts = accs_df[accs_df["account_id"].isin(involved_accounts)]

    engine = get_scoring_engine()
    sc = engine.score_case(
        case=row.to_dict(),
        transactions=scoring_txs,
        accounts=scoring_accounts,
        baseline_transactions=scoring_txs,
    )

    return {
        "case_id": case_id,
        "reported_date": str(row["reported_date"]),
        "reported_amount_paise": int(row["reported_amount_paise"]),
        "reported_amount_inr": int(row["reported_amount_paise"]) / 100.0,
        "status": str(row["status"]),
        "transaction_count": len(case_txs),
        "origin_transaction_id": origin_tx,
        "priority_score": sc.to_dict(),
        "transactions": [
            {
                "transaction_id": str(tx["transaction_id"]),
                "timestamp": str(tx["timestamp"]),
                "from_account": str(tx["from_account"]),
                "to_account": str(tx["to_account"]),
                "amount_paise": int(tx["amount_paise"]),
                "amount_inr": int(tx["amount_paise"]) / 100.0,
                "transaction_type": str(tx["transaction_type"]),
                "evidence_status": str(tx["evidence_status"]),
            }
            for _, tx in case_txs.iterrows()
        ],
    }


@app.get("/api/transactions", response_model=PaginatedTransactions)
def list_transactions(
    request: Request,
    case_id: Optional[str] = None,
    account_id: Optional[str] = None,
    transaction_type: Optional[str] = None,
    evidence_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_current_user),
):
    """Searches and filters transactions across the validated ledger."""
    client_ip = request.client.host if request.client else "unknown"
    if case_id:
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    txs_df = data["transactions_df"]

    filtered = txs_df.copy()
    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        # Unscoped listings are restricted to the investigator's assigned cases.
        filtered = filtered[filtered["case_id"].isin(auth.user.assigned_cases)]

    if case_id:
        filtered = filtered[filtered["case_id"] == case_id]
    if account_id:
        filtered = filtered[
            (filtered["from_account"] == account_id) | (filtered["to_account"] == account_id)
        ]
    if transaction_type:
        filtered = filtered[filtered["transaction_type"] == transaction_type]
    if evidence_status:
        filtered = filtered[filtered["evidence_status"] == evidence_status]
    if search:
        s = search.strip().lower()
        filtered = filtered[
            filtered["transaction_id"].str.lower().str.contains(s)
            | filtered["from_account"].str.lower().str.contains(s)
            | filtered["to_account"].str.lower().str.contains(s)
        ]

    total = len(filtered)
    paged = filtered.iloc[offset : offset + limit]

    items = []
    for _, tx in paged.iterrows():
        items.append(
            TransactionItem(
                transaction_id=str(tx["transaction_id"]),
                timestamp=str(tx["timestamp"]),
                from_account=str(tx["from_account"]),
                to_account=str(tx["to_account"]),
                amount_paise=int(tx["amount_paise"]),
                amount_inr=int(tx["amount_paise"]) / 100.0,
                transaction_type=str(tx["transaction_type"]),
                case_id=str(tx["case_id"]) if pd.notna(tx.get("case_id")) and str(tx["case_id"]).strip() else None,
                evidence_status=str(tx["evidence_status"]),
            )
        )

    return PaginatedTransactions(
        total=total,
        offset=offset,
        limit=limit,
        items=items,
    )


@app.get("/api/transactions/{transaction_id}")
def get_transaction_detail(
    transaction_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """Fetches details for a single transaction including account flags."""
    data = get_ledger_data()
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    match = txs_df[txs_df["transaction_id"] == transaction_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found.")

    tx = match.iloc[0]
    tx_case = str(tx.get("case_id", "")).strip() if pd.notna(tx.get("case_id")) else ""
    if auth.user.role == Role.INVESTIGATOR:
        if not tx_case:
            raise HTTPException(status_code=403, detail="This transaction is not assigned to an accessible investigation case.")
        check_case_access(tx_case, auth, endpoint="/api/transactions/" + transaction_id, method="GET",
                          client_ip="unknown")
    elif tx_case:
        check_case_access(tx_case, auth, endpoint="/api/transactions/" + transaction_id, method="GET",
                          client_ip="unknown")
    fa = str(tx["from_account"])
    ta = str(tx["to_account"])

    fa_match = accs_df[accs_df["account_id"] == fa]
    ta_match = accs_df[accs_df["account_id"] == ta]

    return {
        "transaction_id": str(tx["transaction_id"]),
        "timestamp": str(tx["timestamp"]),
        "from_account": fa,
        "from_account_type": fa_match.iloc[0]["account_type"] if not fa_match.empty else "external",
        "from_history_complete": bool(fa_match.iloc[0]["history_complete"]) if not fa_match.empty else None,
        "to_account": ta,
        "to_account_type": ta_match.iloc[0]["account_type"] if not ta_match.empty else "external",
        "to_history_complete": bool(ta_match.iloc[0]["history_complete"]) if not ta_match.empty else None,
        "amount_paise": int(tx["amount_paise"]),
        "amount_inr": int(tx["amount_paise"]) / 100.0,
        "transaction_type": str(tx["transaction_type"]),
        "case_id": str(tx["case_id"]) if pd.notna(tx.get("case_id")) and str(tx["case_id"]).strip() else None,
        "evidence_status": str(tx["evidence_status"]),
    }


@app.get("/api/accounts", response_model=List[AccountItem])
def list_accounts(
    request: Request,
    case_id: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
):
    """Return accounts in the requested scope; investigators cannot fetch a global account inventory."""
    data = get_ledger_data()
    accs_df = data["accounts_df"]
    txs_df = data["transactions_df"]
    final_balances = data["final_balances"]
    client_ip = request.client.host if request.client else "unknown"

    if case_id:
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)
        scoped_txs = txs_df[txs_df["case_id"] == case_id]
    elif auth.user.role == Role.INVESTIGATOR:
        raise HTTPException(status_code=400, detail="case_id is required when listing accounts as an investigator.")
    else:
        scoped_txs = txs_df

    involved_ids = set(scoped_txs["from_account"]).union(set(scoped_txs["to_account"]))
    results = []
    for _, acc in accs_df.iterrows():
        aid = str(acc["account_id"])
        if case_id and aid not in involved_ids:
            continue

        if auth.user.role == Role.INVESTIGATOR:
            # Do not expose account-wide balances if the account appears in any out-of-scope or unassigned event.
            related = txs_df[(txs_df["from_account"] == aid) | (txs_df["to_account"] == aid)]
            related_case_ids = set(related["case_id"].fillna("").astype(str).str.strip())
            allowed_scope = {case_id} if case_id else set(auth.user.assigned_cases)
            if not related_case_ids or "" in related_case_ids or not related_case_ids.issubset(allowed_scope):
                continue

        opening = int(acc["opening_balance_paise"])
        final = int(final_balances.get(aid, opening))
        results.append(
            AccountItem(
                account_id=aid,
                account_type=str(acc["account_type"]),
                opening_balance_paise=opening,
                opening_balance_inr=opening / 100.0,
                final_balance_paise=final,
                final_balance_inr=final / 100.0,
                history_complete=bool(acc["history_complete"]),
                is_external=aid.startswith(EXTERNAL_ACCOUNT_PREFIX),
            )
        )
    return results


@app.get("/api/accounts/{account_id}/balance-history", response_model=List[BalanceEventItem])
def get_account_balance_history(
    account_id: str,
    request: Request,
    case_id: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
):
    """Return authorized balance history; refuse account-wide history that crosses investigator scope."""
    data = get_ledger_data()
    events = data["balance_events"]
    txs_df = data["transactions_df"]
    client_ip = request.client.host if request.client else "unknown"

    if auth.user.role == Role.INVESTIGATOR and not case_id:
        raise HTTPException(status_code=400, detail="case_id is required when requesting balance history as an investigator.")
    if case_id:
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    related = txs_df[(txs_df["from_account"] == account_id) | (txs_df["to_account"] == account_id)]
    if related.empty:
        if data["accounts_df"][data["accounts_df"]["account_id"] == account_id].empty:
            raise HTTPException(status_code=404, detail="Account not found.")
        return []

    if auth.user.role == Role.INVESTIGATOR:
        related_case_ids = set(related["case_id"].fillna("").astype(str).str.strip())
        if "" in related_case_ids or not related_case_ids.issubset(set(auth.user.assigned_cases)):
            raise HTTPException(status_code=403, detail="Account history includes events outside the authorized case scope.")
    if case_id:
        related_case_ids = set(related["case_id"].fillna("").astype(str).str.strip())
        if auth.user.role == Role.INVESTIGATOR:
            allowed_scope = {case_id} if case_id else set(auth.user.assigned_cases)
            if "" in related_case_ids or not related_case_ids.issubset(allowed_scope):
                raise HTTPException(status_code=403, detail="Account-wide balances cannot be shown because this account spans additional case records.")
        matched_events = [e for e in events if e.account_id == account_id and e.case_id == case_id]
    else:
        matched_events = [e for e in events if e.account_id == account_id]

    return [
        BalanceEventItem(
            account_id=e.account_id,
            timestamp=e.timestamp,
            transaction_id=e.transaction_id,
            counterparty_account=e.counterparty_account,
            balance_before_paise=e.balance_before_paise,
            balance_before_inr=e.balance_before_paise / 100.0,
            amount_change_paise=e.amount_change_paise,
            amount_change_inr=e.amount_change_paise / 100.0,
            balance_after_paise=e.balance_after_paise,
            balance_after_inr=e.balance_after_paise / 100.0,
            direction=e.direction,
            transaction_type=e.transaction_type,
            case_id=e.case_id,
            evidence_status=e.evidence_status,
        )
        for e in matched_events
    ]


@app.get("/api/graph", response_model=GraphResponse)
def get_transaction_graph(
    request: Request,
    case_id: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
):
    """Return directed ledger edges; case mode expands a time-ordered reachable flow from the source event."""
    client_ip = request.client.host if request.client else "unknown"
    if case_id:
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    accounts_df = data["accounts_df"]
    transactions_df = data["transactions_df"]
    final_balances = data["final_balances"]

    source_transaction_id: Optional[str] = None
    source_amount_inr: Optional[float] = None
    flow_scope: Optional[str] = None
    selected_rows: List[Dict[str, Any]] = []
    node_levels: Dict[str, int] = {}
    source_accounts: set[str] = set()

    if case_id:
        cases_df = data["cases_df"]
        if cases_df[cases_df["case_id"].astype(str) == case_id].empty:
            raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

        case_rows = transactions_df[transactions_df["case_id"].fillna("").astype(str).str.strip() == case_id].copy()
        if case_rows.empty:
            raise HTTPException(status_code=404, detail=f"No ledger transactions are linked to case '{case_id}'.")
        origin = select_case_source_transaction(case_rows)
        if origin is None:
            raise HTTPException(status_code=404, detail=f"No source transaction is available for case '{case_id}'.")
        source_transaction_id = str(origin["transaction_id"])
        source_amount_paise = int(origin["amount_paise"])
        origin_timestamp = pd.to_datetime(origin["timestamp"], utc=True, errors="coerce")
        origin_from = str(origin["from_account"])
        origin_to = str(origin["to_account"])
        source_accounts.add(origin_from)
        node_levels[origin_from] = 0
        node_levels[origin_to] = 1

        # Seed with the source event. Then follow later debits from every reached account.
        # The edge still shows the full recorded transaction amount; this is not the
        # amount attributed to the original source lot. Attribution remains in Consensus Lien.
        selected_by_id: Dict[str, Dict[str, Any]] = {
            source_transaction_id: {
                **origin.drop(labels=["_flow_ts"], errors="ignore").to_dict(),
                "_flow_hop": 1,
                "_linkage_basis": "CASE_REFERENCE",
                "_is_source_transaction": True,
            }
        }

        all_rows = transactions_df.copy()
        # Never traverse records assigned to a different case when the requester is a
        # case-scoped investigator. Unassigned ledger entries may be shown only as
        # contextual statement activity on an already reached account.
        if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
            row_case_ids = all_rows["case_id"].fillna("").astype(str).str.strip()
            allowed_case_ids = set(auth.user.assigned_cases)
            all_rows = all_rows[(row_case_ids == "") | row_case_ids.isin(allowed_case_ids)]
        all_rows["_flow_ts"] = pd.to_datetime(all_rows["timestamp"], utc=True, errors="coerce")
        all_rows = all_rows.sort_values(["_flow_ts", "transaction_id"], kind="stable")
        queue: List[Tuple[str, Any, int]] = [(origin_to, origin_timestamp, 1)]
        visited_states: set[Tuple[str, str, int]] = set()
        max_hops = 6
        max_edges = 40

        while queue and len(selected_by_id) < max_edges:
            account_id, arrived_at, current_level = queue.pop(0)
            arrival_key = arrived_at.isoformat() if not pd.isna(arrived_at) else "unknown-time"
            state_key = (account_id, arrival_key, current_level)
            if state_key in visited_states:
                continue
            visited_states.add(state_key)
            if current_level >= max_hops:
                continue

            outbound = all_rows[
                (all_rows["from_account"].astype(str) == account_id)
                & all_rows["_flow_ts"].notna()
                & (all_rows["_flow_ts"] > arrived_at)
            ]
            for _, tx in outbound.iterrows():
                tx_id = str(tx["transaction_id"])
                if tx_id == source_transaction_id:
                    continue
                next_hop = current_level + 1
                if tx_id not in selected_by_id:
                    tx_case = str(tx.get("case_id", "")).strip() if pd.notna(tx.get("case_id")) else ""
                    selected_by_id[tx_id] = {
                        **tx.drop(labels=["_flow_ts"], errors="ignore").to_dict(),
                        "_flow_hop": next_hop,
                        "_linkage_basis": "CASE_REFERENCE" if tx_case == case_id else "CHRONOLOGICALLY_REACHABLE",
                        "_is_source_transaction": False,
                    }
                destination = str(tx["to_account"])
                previous_level = node_levels.get(destination)
                if previous_level is None or next_hop < previous_level:
                    node_levels[destination] = next_hop
                if len(selected_by_id) >= max_edges:
                    break
                queue.append((destination, tx["_flow_ts"], next_hop))

            # Also surface later credits into the reached account. These matter for
            # commingling analysis, but are explicitly tagged as account context and
            # are not treated as a hop originating from the suspicious source.
            context_rows = all_rows[
                (all_rows["to_account"].astype(str) == account_id)
                & all_rows["_flow_ts"].notna()
                & (all_rows["_flow_ts"] > arrived_at)
            ]
            for _, tx in context_rows.iterrows():
                if len(selected_by_id) >= max_edges:
                    break
                tx_id = str(tx["transaction_id"])
                if tx_id == source_transaction_id or tx_id in selected_by_id:
                    continue
                selected_by_id[tx_id] = {
                    **tx.drop(labels=["_flow_ts"], errors="ignore").to_dict(),
                    "_flow_hop": None,
                    "_linkage_basis": "ACCOUNT_CONTEXT",
                    "_is_source_transaction": False,
                }
                context_source = str(tx["from_account"])
                node_levels.setdefault(context_source, max(0, current_level - 1))
                if len(selected_by_id) >= max_edges:
                    break

        selected_rows = list(selected_by_id.values())
        flow_scope = (
            f"Source {source_transaction_id}, subsequent time-ordered outgoing events reachable within "
            f"{max_hops} hops, and later credits into reached accounts for commingling context (maximum {max_edges} edges). "
            "A chronologically reachable edge is a candidate path, while an account-context edge shows a related credit; "
            "neither proves that the full transaction amount came from the source funds."
        )
        source_amount_inr = source_amount_paise / 100.0
    else:
        if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
            filtered = transactions_df[transactions_df["case_id"].fillna("").astype(str).isin(auth.user.assigned_cases)]
        else:
            filtered = transactions_df
        for _, tx in filtered.iterrows():
            selected_rows.append({
                **tx.to_dict(),
                "_flow_hop": None,
                "_linkage_basis": "LEDGER_RECORD",
                "_is_source_transaction": False,
            })

    # Ensure chronological rendering and stable transaction IDs in the response.
    selected_rows.sort(key=lambda tx: (str(tx.get("timestamp", "")), str(tx.get("transaction_id", ""))))
    involved_account_ids = set()
    flagged_account_ids = set()
    for tx in selected_rows:
        from_id = str(tx["from_account"])
        to_id = str(tx["to_account"])
        involved_account_ids.add(from_id)
        involved_account_ids.add(to_id)
        if str(tx.get("evidence_status", "")).strip().lower() == "suspected_fraud":
            # Flag the receiving node on a suspected transfer, not the sending victim/source.
            if to_id not in source_accounts:
                flagged_account_ids.add(to_id)

    account_map = {str(row["account_id"]): row for _, row in accounts_df.iterrows()}
    nodes: List[GraphNode] = []
    for account_id in sorted(involved_account_ids, key=lambda aid: (node_levels.get(aid, 99), aid)):
        is_external = account_id.startswith(EXTERNAL_ACCOUNT_PREFIX) or account_id not in account_map
        opening_balance = None
        final_balance = None
        history_complete = None
        account_type = "external"
        if account_id in account_map:
            account_info = account_map[account_id]
            account_type = str(account_info["account_type"])
            if auth.user.role != Role.INVESTIGATOR:
                opening_balance = int(account_info["opening_balance_paise"])
                final_balance = int(final_balances.get(account_id, opening_balance))
                history_complete = bool(account_info["history_complete"])
            else:
                related = transactions_df[
                    (transactions_df["from_account"].astype(str) == account_id)
                    | (transactions_df["to_account"].astype(str) == account_id)
                ]
                related_case_ids = set(related["case_id"].fillna("").astype(str).str.strip())
                allowed_scope = {case_id} if case_id else set(auth.user.assigned_cases)
                if related_case_ids and "" not in related_case_ids and related_case_ids.issubset(allowed_scope):
                    opening_balance = int(account_info["opening_balance_paise"])
                    final_balance = int(final_balances.get(account_id, opening_balance))
                    history_complete = bool(account_info["history_complete"])

        nodes.append(GraphNode(
            id=account_id,
            label=account_id,
            type=account_type,
            is_external=is_external,
            opening_balance_inr=(opening_balance / 100.0) if opening_balance is not None else None,
            final_balance_inr=(final_balance / 100.0) if final_balance is not None else None,
            history_complete=history_complete,
            flow_level=node_levels.get(account_id) if case_id else None,
            is_origin_account=(account_id in source_accounts),
            flagged_by_case_evidence=(account_id in flagged_account_ids) if case_id else False,
        ))

    edges: List[GraphEdge] = []
    for tx in selected_rows:
        amount_paise = int(tx["amount_paise"])
        tx_case = str(tx.get("case_id", "")).strip() if pd.notna(tx.get("case_id")) else ""
        edges.append(GraphEdge(
            id=str(tx["transaction_id"]),
            source=str(tx["from_account"]),
            target=str(tx["to_account"]),
            amount_paise=amount_paise,
            amount_inr=amount_paise / 100.0,
            timestamp=str(tx["timestamp"]),
            transaction_type=str(tx["transaction_type"]),
            case_id=tx_case,
            evidence_status=str(tx.get("evidence_status", "unflagged")),
            flow_hop=tx.get("_flow_hop"),
            linkage_basis=str(tx.get("_linkage_basis", "LEDGER_RECORD")),
            is_source_transaction=bool(tx.get("_is_source_transaction", False)),
        ))

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        source_transaction_id=source_transaction_id,
        source_amount_inr=source_amount_inr,
        flow_scope=flow_scope,
    )


@app.get("/api/consensus-lien/{case_id}", response_model=ConsensusLienResponse)
def get_consensus_lien(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
):
    """Executes Proportional, FIFO, and LIBR tracing and generates Consensus Lien bounds."""
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    matched = cases_df[cases_df["case_id"] == case_id]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    case_txs = txs_df[txs_df["case_id"] == case_id]
    if case_txs.empty:
        raise HTTPException(status_code=400, detail=f"No transactions linked to case '{case_id}'.")

    origin_tx = select_case_source_transaction(case_txs)
    if origin_tx is None:
        raise HTTPException(status_code=400, detail=f"No source transaction is available for case '{case_id}'.")
    origin_tx_id = str(origin_tx["transaction_id"])
    origin_amt = int(origin_tx["amount_paise"])

    # Run all three methods independently and compare via Consensus Lien Engine
    lien_res = ConsensusLienEngine.run_all_methods(
        accounts=accs_df,
        transactions=txs_df,
        source_transaction_id=origin_tx_id,
        source_case_id=case_id,
    )

    # Generate structured explanation
    explanation = {
        "summary": (
            f"Case {case_id} Consensus Lien evaluated across {len(lien_res.account_liens)} accounts. "
            f"Total lower bound: ₹{lien_res.total_lower_retained_paise / 100:,.2f}, "
            f"joint-feasible upper bound: ₹{lien_res.joint_feasible_upper_paise / 100:,.2f} "
            f"(unconstrained per-account sum: ₹{lien_res.total_upper_retained_paise / 100:,.2f}, "
            f"confirmed external outflows: ₹{lien_res.confirmed_withdrawn_paise / 100:,.2f}), "
            f"joint disagreement: ₹{(lien_res.joint_feasible_upper_paise - lien_res.total_lower_retained_paise) / 100:,.2f}."
        ),
        "account_explanations": {
            aid: acl.explanation_text for aid, acl in lien_res.account_liens.items()
        },
        "assumptions": lien_res.assumptions_and_limitations,
    }

    account_liens = []
    acc_map = {str(r["account_id"]): r for _, r in accs_df.iterrows()}

    for aid, acl in lien_res.account_liens.items():
        is_ext = aid.startswith(EXTERNAL_ACCOUNT_PREFIX)
        hist_comp = bool(acc_map[aid]["history_complete"]) if aid in acc_map else True

        account_liens.append(
            AccountLienItem(
                account_id=aid,
                proportional_paise=acl.proportional_paise,
                proportional_inr=acl.proportional_paise / 100.0,
                fifo_paise=acl.fifo_paise,
                fifo_inr=acl.fifo_paise / 100.0,
                libr_paise=acl.libr_paise,
                libr_inr=acl.libr_paise / 100.0,
                lower_bound_paise=acl.lower_estimate_paise,
                lower_bound_inr=acl.lower_estimate_paise / 100.0,
                upper_bound_paise=acl.upper_estimate_paise,
                upper_bound_inr=acl.upper_estimate_paise / 100.0,
                disagreement_paise=acl.disagreement_paise,
                disagreement_inr=acl.disagreement_paise / 100.0,
                is_external=is_ext,
                history_complete=hist_comp,
            )
        )

    # Sort account liens by lower bound descending
    account_liens.sort(key=lambda x: x.lower_bound_paise, reverse=True)

    joint_upper_paise = lien_res.joint_feasible_upper_paise
    joint_lower_paise = lien_res.total_lower_retained_paise
    joint_disagree_paise = max(0, joint_upper_paise - joint_lower_paise)

    return ConsensusLienResponse(
        case_id=case_id,
        source_transaction_id=origin_tx_id,
        source_amount_paise=origin_amt,
        source_amount_inr=origin_amt / 100.0,
        consensus_status=lien_res.status,
        total_lower_bound_paise=joint_lower_paise,
        total_lower_bound_inr=joint_lower_paise / 100.0,
        total_upper_bound_paise=joint_upper_paise,
        total_upper_bound_inr=joint_upper_paise / 100.0,
        total_disagreement_paise=joint_disagree_paise,
        total_disagreement_inr=joint_disagree_paise / 100.0,
        joint_feasible_upper_paise=joint_upper_paise,
        joint_feasible_upper_inr=joint_upper_paise / 100.0,
        confirmed_withdrawn_paise=lien_res.confirmed_withdrawn_paise,
        confirmed_withdrawn_inr=lien_res.confirmed_withdrawn_paise / 100.0,
        unconstrained_upper_bound_paise=lien_res.total_upper_retained_paise,
        unconstrained_upper_bound_inr=lien_res.total_upper_retained_paise / 100.0,
        account_liens=account_liens,
        method_details={
            "proportional": {"status": "COMPLETED", "assumption": "Fungible commingling across concurrent balance"},
            "fifo": {"status": "COMPLETED", "assumption": "Oldest source lots consumed first in chronological order"},
            "libr": {"status": "COMPLETED", "assumption": "Clean funds dissipate first with irreversible lowest intermediate balance ceiling"},
        },
        explanation=explanation,
        governance_notice=GOVERNANCE_DISCLAIMER,
    )


@app.get("/api/cases/{case_id}/recommendations", response_model=CaseRecommendationsResponse)
@app.get("/api/recommendations/{case_id}", response_model=CaseRecommendationsResponse)
def get_case_recommendations(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
    policy: str = Query("balanced", description="Policy dial: conservative, balanced, or aggressive"),
    de_minimis_paise: Optional[int] = Query(None, description="Optional override for de-minimis threshold in paise"),
) -> CaseRecommendationsResponse:
    """Computes explainable, safeguard-guaranteed action recommendations per account.

    Core: Minimum across Proportional, FIFO, and LIBR.
    Margin: Disagreement range within joint cap.
    Safeguards:
    - Harm signals and evidence only reduce the margin, never the core.
    - Uploaded documents never release anything alone.
    - Accounts below de-minimis total stolen amount get tracking, not a hold.
    - If core is 0, margin is large, and mule score is high, recommend time-boxed margin hold needing approval.
    """
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    matched = cases_df[cases_df["case_id"] == case_id]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    case_txs = txs_df[txs_df["case_id"] == case_id]
    if case_txs.empty:
        raise HTTPException(status_code=400, detail=f"No transactions linked to case '{case_id}'.")

    origin_tx = select_case_source_transaction(case_txs)
    if origin_tx is None:
        raise HTTPException(status_code=400, detail=f"No source transaction is available for case '{case_id}'.")
    origin_tx_id = str(origin_tx["transaction_id"])

    engine = DecisionEngine()
    result = engine.evaluate_case(
        case_id=case_id,
        accounts=accs_df,
        transactions=txs_df,
        source_transaction_id=origin_tx_id,
        policy_name=policy,
        mule_scores=None,  # Automatically predicts using trained interpretable MuleDetectorService
        override_de_minimis=de_minimis_paise,
    )

    # Build minimal ledger slice for this case's recommendations
    case_tx_records = case_txs.to_dict(orient="records")
    connected_acc_ids = {str(t.get("from_account")) for t in case_tx_records} | {str(t.get("to_account")) for t in case_tx_records}
    slice_accounts = [dict(a) for a in accs_df.to_dict(orient="records") if str(a.get("account_id")) in connected_acc_ids]
    ledger_slice = {
        "accounts": slice_accounts,
        "transactions": case_tx_records,
    }

    # Fetch consensus bounds for per-method breakdown
    consensus_res = ConsensusLienEngine.run_all_methods(
        accounts=accs_df,
        transactions=txs_df,
        source_transaction_id=origin_tx_id,
        source_case_id=case_id,
    )

    for rec in result.recommendations:
        if rec.action != "none" or rec.core > 0 or rec.held_margin_paise > 0:
            lien = consensus_res.account_liens.get(rec.account_id)
            per_method = {
                "proportional": {"lower_paise": lien.proportional_paise if lien else 0, "upper_paise": lien.proportional_paise if lien else 0},
                "fifo": {"lower_paise": lien.fifo_paise if lien else 0, "upper_paise": lien.fifo_paise if lien else 0},
                "libr": {"lower_paise": lien.libr_paise if lien else 0, "upper_paise": lien.libr_paise if lien else 0},
            }
            receipt = create_hold_receipt(
                case_id=case_id,
                account_id=rec.account_id,
                source_transaction_id=origin_tx_id,
                action=rec.action,
                core_paise=rec.core,
                margin_paise=rec.margin,
                policy_name=policy,
                policy_version=result.policy_version,
                rules_fired=rec.reasons,
                approver=auth.user.user_id,
                per_method_results=per_method,
                ledger_slice=ledger_slice,
            )
            rec.receipt_id = receipt["receipt_id"]

    return CaseRecommendationsResponse(**result.to_dict())


def _build_hold_preview(case_id: str, request: Request, auth: AuthContext) -> HoldPreviewResponse:
    if not DEMO_AUTH_ENABLED or ENV_MODE not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Simulated hold proposals are available only in explicitly enabled local demo mode.")

    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method=request.method, client_ip=client_ip)

    graph = get_transaction_graph(request=request, case_id=case_id, auth=auth)
    consensus = get_consensus_lien(case_id=case_id, request=request, auth=auth)
    ledger = get_ledger_data()
    accounts_df = ledger["accounts_df"]
    final_balances = ledger["final_balances"]
    account_map = {str(row["account_id"]): row for _, row in accounts_df.iterrows()}
    graph_accounts = {node.id for node in graph.nodes}
    linked_suspicious: Dict[str, List[str]] = {}
    for edge in graph.edges:
        if edge.evidence_status.strip().lower() == "suspected_fraud":
            linked_suspicious.setdefault(edge.source, []).append(edge.id)
            linked_suspicious.setdefault(edge.target, []).append(edge.id)

    candidates: List[HoldCandidateResponse] = []
    for lien in consensus.account_liens:
        account_id = lien.account_id
        if account_id not in graph_accounts or lien.is_external:
            continue

        row = account_map.get(account_id)
        history_complete = bool(row["history_complete"]) if row is not None else None
        current_balance = int(final_balances.get(account_id, 0)) if row is not None else None
        proposed_hold = min(max(int(lien.lower_bound_paise), 0), max(current_balance or 0, 0))
        reasons: List[str] = []
        if row is None:
            reasons.append("Account is not in the operational ledger.")
        if history_complete is not True:
            reasons.append("Account statement history is incomplete or unavailable.")
        if current_balance is None or current_balance <= 0:
            reasons.append("No positive current ledger balance is available.")
        if lien.lower_bound_paise <= 0:
            reasons.append("The conservative tracing lower bound is zero.")
        if proposed_hold <= 0 and not reasons:
            reasons.append("No positive hold amount can be calculated.")

        eligible = not reasons and proposed_hold > 0
        candidates.append(HoldCandidateResponse(
            account_id=account_id,
            account_type=str(row["account_type"]) if row is not None else "unknown",
            current_balance_paise=current_balance,
            current_balance_inr=(current_balance / 100.0) if current_balance is not None else None,
            lower_bound_paise=int(lien.lower_bound_paise),
            lower_bound_inr=int(lien.lower_bound_paise) / 100.0,
            upper_bound_paise=int(lien.upper_bound_paise),
            upper_bound_inr=int(lien.upper_bound_paise) / 100.0,
            proposed_hold_paise=proposed_hold if eligible else 0,
            proposed_hold_inr=(proposed_hold / 100.0) if eligible else 0.0,
            history_complete=history_complete,
            is_eligible=eligible,
            eligibility_reason="Eligible for a local simulated proposal." if eligible else " ".join(reasons),
            linked_suspicious_transaction_ids=sorted(set(linked_suspicious.get(account_id, []))),
        ))

    candidates.sort(key=lambda item: (not item.is_eligible, -item.proposed_hold_paise, item.account_id))
    return HoldPreviewResponse(
        case_id=case_id,
        source_transaction_id=consensus.source_transaction_id,
        source_amount_paise=consensus.source_amount_paise,
        source_amount_inr=consensus.source_amount_inr,
        consensus_status=consensus.consensus_status,
        candidates=candidates,
        formula="Proposed amount = min(account-level Consensus Lien lower bound, current reconstructed ledger balance); only complete-history, positive-balance accounts are eligible.",
        execution_status="SIMULATION_ONLY_NOT_SENT_TO_BANK",
        disclaimer="This is a local demonstration proposal, not a legal freeze or bank instruction. It does not reserve, transfer, block, or freeze real funds. Authorized review and a real institution API would be required.",
    )


@app.get("/api/hold-preview/{case_id}", response_model=HoldPreviewResponse)
def get_hold_preview(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
) -> HoldPreviewResponse:
    """Calculate eligible simulated hold amounts from current ledger and consensus output."""
    return _build_hold_preview(case_id, request, auth)


@app.post("/api/hold-proposals", response_model=DemoHoldProposalResponse)
def create_demo_hold_proposal(
    payload: DemoHoldProposalRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
) -> DemoHoldProposalResponse:
    """Record a simulated hold proposal with audit telemetry; never communicates with a bank."""
    if not DEMO_AUTH_ENABLED or ENV_MODE not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Simulated hold proposals are available only in explicitly enabled local demo mode.")

    preview = _build_hold_preview(payload.case_id, request, auth)
    candidate = next((item for item in preview.candidates if item.account_id == payload.account_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Account is not an eligible candidate in this case's graph.")
    if not candidate.is_eligible:
        raise HTTPException(status_code=409, detail=candidate.eligibility_reason)
    if candidate.proposed_hold_paise <= 0:
        raise HTTPException(status_code=422, detail="The calculated hold proposal must be positive.")

    client_ip = request.client.host if request.client else "unknown"
    now = pd.Timestamp.now(tz="UTC").isoformat()
    proposal_id = f"HOLD_SIM_{uuid.uuid4().hex[:10].upper()}"
    calculation = "min(account-level Consensus Lien lower bound, reconstructed closing ledger balance)"
    event = SecurityAuditLogger.get_instance().log_event(
        event_type="SIMULATED_HOLD_PROPOSAL_CREATED",
        endpoint=request.url.path,
        method="POST",
        severity=AuditSeverity.INFO,
        user_id=auth.user.user_id,
        user_role=auth.user.role.value,
        ip_address=client_ip,
        details={
            "proposal_id": proposal_id,
            "case_id": payload.case_id,
            "account_id": payload.account_id,
            "source_transaction_id": preview.source_transaction_id,
            "proposed_hold_paise": candidate.proposed_hold_paise,
            "execution_status": "SIMULATION_ONLY_NOT_SENT_TO_BANK",
        },
    )
    record = {
        "proposal_id": proposal_id,
        "audit_event_id": event.event_id,
        "created_at": now,
        "case_id": payload.case_id,
        "source_transaction_id": preview.source_transaction_id,
        "account_id": payload.account_id,
        "current_balance_paise": int(candidate.current_balance_paise or 0),
        "current_balance_inr": int(candidate.current_balance_paise or 0) / 100.0,
        "consensus_lower_bound_paise": candidate.lower_bound_paise,
        "consensus_lower_bound_inr": candidate.lower_bound_inr,
        "proposed_hold_paise": candidate.proposed_hold_paise,
        "proposed_hold_inr": candidate.proposed_hold_inr,
        "calculation": calculation,
        "status": "SIMULATED_PENDING_AUTHORIZED_REVIEW",
        "execution_status": "SIMULATION_ONLY_NOT_SENT_TO_BANK",
        "message": "Proposal recorded for demonstration. No bank API was called and no funds were frozen.",
    }

    # Generate cryptographic approval receipt
    ledger = get_ledger_data()
    accounts_df = ledger["accounts_df"]
    prop_txs = ledger["transactions_df"][ledger["transactions_df"]["case_id"] == payload.case_id]
    prop_tx_records = prop_txs.to_dict(orient="records")
    prop_acc_ids = {str(t.get("from_account")) for t in prop_tx_records} | {str(t.get("to_account")) for t in prop_tx_records}
    prop_acc_records = [dict(a) for a in accounts_df.to_dict(orient="records") if str(a.get("account_id")) in prop_acc_ids]
    prop_slice = {
        "accounts": prop_acc_records,
        "transactions": prop_tx_records,
    }
    prop_per_method = {
        "proportional": {"lower_paise": candidate.lower_bound_paise, "upper_paise": candidate.upper_bound_paise},
        "fifo": {"lower_paise": candidate.lower_bound_paise, "upper_paise": candidate.upper_bound_paise},
        "libr": {"lower_paise": candidate.lower_bound_paise, "upper_paise": candidate.upper_bound_paise},
    }
    prop_receipt = create_hold_receipt(
        case_id=payload.case_id,
        account_id=payload.account_id,
        source_transaction_id=preview.source_transaction_id,
        action="hold_approval",
        core_paise=candidate.proposed_hold_paise,
        margin_paise=0,
        policy_name="balanced",
        policy_version="1.0.0",
        rules_fired=["authorized_investigator_hold_proposal"],
        approver=auth.user.user_id,
        per_method_results=prop_per_method,
        ledger_slice=prop_slice,
    )
    record["receipt_id"] = prop_receipt["receipt_id"]

    DEMO_HOLD_PROPOSALS.append(record)
    del DEMO_HOLD_PROPOSALS[:-200]
    return DemoHoldProposalResponse(**record)


@app.get("/api/hold-proposals", response_model=List[DemoHoldProposalResponse])
def list_demo_hold_proposals(
    request: Request,
    case_id: Optional[str] = None,
    auth: AuthContext = Depends(get_current_user),
) -> List[DemoHoldProposalResponse]:
    """List in-memory demo proposals for authorized cases in this running process."""
    if not DEMO_AUTH_ENABLED or ENV_MODE not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Simulated hold proposals are available only in explicitly enabled local demo mode.")
    if case_id:
        client_ip = request.client.host if request.client else "unknown"
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)
    visible = [
        DemoHoldProposalResponse(**item) for item in DEMO_HOLD_PROPOSALS
        if auth.can_access_case(str(item["case_id"]))
        and (not case_id or item["case_id"] == case_id)
    ]
    return visible


@app.get("/api/investigation-priority", response_model=List[PriorityScoreResponse])
def get_investigation_priority_rankings(
    auth: AuthContext = Depends(get_current_user),
):
    """Returns ranked investigation priority scores across all authorized cases."""
    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    # Score only within the investigator's authorized case data scope.
    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        cases_df = cases_df[cases_df["case_id"].isin(auth.user.assigned_cases)]
        txs_df = txs_df[txs_df["case_id"].isin(auth.user.assigned_cases)]
        involved_accounts = set(txs_df["from_account"]).union(set(txs_df["to_account"]))
        accs_df = accs_df[accs_df["account_id"].isin(involved_accounts)]

    engine = get_scoring_engine()
    scores = engine.score_all_cases(cases_df, txs_df, accs_df)
    ranked = engine.rank_cases(scores)

    results = []
    for s in ranked:
        results.append(
            PriorityScoreResponse(
                case_id=s.case_id,
                final_score=s.final_score,
                priority_band=s.priority_band,
                status=s.status,
                evidence_coverage=s.evidence_coverage,
                reported_amount_paise=s.reported_amount_paise,
                reported_amount_inr=s.reported_amount_paise / 100.0,
                reported_date=s.reported_date,
                component_b=s.component_b.to_dict(),
                component_t=s.component_t.to_dict(),
                component_h=s.component_h.to_dict(),
                missing_components=s.missing_components,
                positive_factors=s.positive_factors,
                mitigating_factors=s.mitigating_factors,
                data_quality_warnings=s.data_quality_warnings,
                supporting_transaction_ids=s.supporting_transaction_ids,
                supporting_account_ids=s.supporting_account_ids,
                disclaimer=s.disclaimer,
            )
        )
    return results


@app.get("/api/investigation-priority/{case_id}", response_model=PriorityScoreResponse)
def get_case_priority_score(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
):
    """Returns detailed investigation priority score and factors with BOLA verification."""
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    matched = cases_df[cases_df["case_id"] == case_id]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    scoring_txs = txs_df
    scoring_accounts = accs_df
    if auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        scoring_txs = txs_df[txs_df["case_id"].isin(auth.user.assigned_cases)]
        involved_accounts = set(scoring_txs["from_account"]).union(set(scoring_txs["to_account"]))
        scoring_accounts = accs_df[accs_df["account_id"].isin(involved_accounts)]

    engine = get_scoring_engine()
    s = engine.score_case(
        case=matched.iloc[0].to_dict(),
        transactions=scoring_txs,
        accounts=scoring_accounts,
        baseline_transactions=scoring_txs,
    )

    return PriorityScoreResponse(
        case_id=s.case_id,
        final_score=s.final_score,
        priority_band=s.priority_band,
        status=s.status,
        evidence_coverage=s.evidence_coverage,
        reported_amount_paise=s.reported_amount_paise,
        reported_amount_inr=s.reported_amount_paise / 100.0,
        reported_date=s.reported_date,
        component_b=s.component_b.to_dict(),
        component_t=s.component_t.to_dict(),
        component_h=s.component_h.to_dict(),
        missing_components=s.missing_components,
        positive_factors=s.positive_factors,
        mitigating_factors=s.mitigating_factors,
        data_quality_warnings=s.data_quality_warnings,
        supporting_transaction_ids=s.supporting_transaction_ids,
        supporting_account_ids=s.supporting_account_ids,
        disclaimer=s.disclaimer,
    )


@app.get("/api/data-quality", response_model=DataQualityResponse)
def get_data_quality(auth: AuthContext = Depends(get_current_user)):
    """Inspect files currently present; external row counts and schema status come from actual CSV contents."""
    datasets: List[DataQualityDatasetItem] = []

    account_path = SYNTHETIC_DIR / "accounts.csv"
    transaction_path = SYNTHETIC_DIR / "transactions.csv"
    case_path = SYNTHETIC_DIR / "cases.csv"
    ledger_profiles = [
        _profile_csv(account_path, CANONICAL_ACCOUNT_COLUMNS),
        _profile_csv(transaction_path, CANONICAL_TRANSACTION_COLUMNS),
        _profile_csv(case_path, CANONICAL_CASE_COLUMNS),
    ]
    ledger_present = sum(1 for item in ledger_profiles if item["exists"])
    ledger_rows = sum(int(item["rows"]) for item in ledger_profiles)
    ledger_schema_valid = ledger_present == 3 and all(item["parsed"] and item["columns_valid"] for item in ledger_profiles)
    ledger_warnings: List[str] = []
    ledger_labels = ("accounts.csv", "transactions.csv", "cases.csv")
    for label, profile, required in zip(
        ledger_labels,
        ledger_profiles,
        (CANONICAL_ACCOUNT_COLUMNS, CANONICAL_TRANSACTION_COLUMNS, CANONICAL_CASE_COLUMNS),
    ):
        if not profile["exists"]:
            ledger_warnings.append("Missing required file: " + label + ".")
        elif not profile["parsed"]:
            ledger_warnings.append("Could not parse " + label + ".")
        elif not profile["columns_valid"]:
            missing = sorted(set(required) - set(profile["columns"]))
            ledger_warnings.append(label + " is missing required columns: " + ", ".join(missing) + ".")
    ledger_status = "SCHEMA_VALIDATED" if ledger_schema_valid else ("NOT_INSTALLED" if ledger_present == 0 else "INCOMPLETE_OR_INVALID")
    if ledger_schema_valid:
        try:
            accounts = pd.read_csv(account_path, usecols=["history_complete"])
            incomplete = int((~accounts["history_complete"].astype(bool)).sum())
            if incomplete:
                ledger_warnings.append(str(incomplete) + " account(s) have incomplete history.")
        except Exception:
            ledger_warnings.append("Could not assess statement-history completeness.")
    datasets.append(DataQualityDatasetItem(
        dataset_name="Smart-Freeze Synthetic Ledger",
        category="Synthetic account-based ledger",
        status=ledger_status,
        file_count=ledger_present,
        total_rows=ledger_rows,
        columns_valid=ledger_schema_valid,
        warnings=ledger_warnings,
        notes="Synthetic demonstration records, not live bank transactions. Counts and schema checks reflect the files currently present.",
    ))

    elliptic_dir = RAW_DIR / "elliptic_bitcoin_dataset"
    elliptic_paths = [
        elliptic_dir / "elliptic_txs_classes.csv",
        elliptic_dir / "elliptic_txs_edgelist.csv",
        elliptic_dir / "elliptic_txs_features.csv",
    ]
    elliptic_profiles = [
        _profile_csv(elliptic_paths[0], ELLIPTIC_CLASSES_COLUMNS),
        _profile_csv(elliptic_paths[1], ELLIPTIC_EDGELIST_COLUMNS),
        _profile_csv(elliptic_paths[2], header=None, expected_column_count=167),
    ]
    elliptic_present = sum(1 for item in elliptic_profiles if item["exists"])
    elliptic_valid = elliptic_present == 3 and all(item["parsed"] and item["columns_valid"] for item in elliptic_profiles)
    elliptic_rows = int(elliptic_profiles[0]["rows"]) if elliptic_profiles[0]["exists"] else 0
    elliptic_warnings = []
    for name, item in zip(("classes", "edgelist", "headerless features"), elliptic_profiles):
        if not item["exists"]:
            elliptic_warnings.append("Elliptic " + name + " file is missing.")
        elif not item["parsed"] or not item["columns_valid"]:
            elliptic_warnings.append("Elliptic " + name + " file failed schema validation.")
    elliptic_warnings.append("Cryptocurrency graph data; it does not represent INR bank balances.")
    datasets.append(DataQualityDatasetItem(
        dataset_name="Elliptic Bitcoin Transaction Graph",
        category="Cryptocurrency transaction graph",
        status="SCHEMA_VALIDATED" if elliptic_valid else ("NOT_INSTALLED" if elliptic_present == 0 else "PARTIAL_OR_INVALID"),
        file_count=elliptic_present,
        total_rows=elliptic_rows,
        columns_valid=elliptic_valid,
        warnings=elliptic_warnings,
        notes="Row count is read from the local classes file. A complete check requires class, edge and 167-column feature files.",
    ))

    alerts_path = RAW_DIR / "synthetic_alerts.csv"
    synthaml_transactions_path = RAW_DIR / "synthetic_transactions.csv"
    alerts_profile = _profile_csv(alerts_path, SYNTHAML_ALERTS_COLUMNS)
    synthaml_transactions_profile = _profile_csv(synthaml_transactions_path)
    synthaml_present = int(alerts_profile["exists"]) + int(synthaml_transactions_profile["exists"])
    synthaml_valid = bool(alerts_profile["exists"] and alerts_profile["parsed"] and alerts_profile["columns_valid"]
                          and synthaml_transactions_profile["exists"] and synthaml_transactions_profile["parsed"])
    synthaml_warnings = []
    if not alerts_profile["exists"]:
        synthaml_warnings.append("synthetic_alerts.csv is not present.")
    elif not alerts_profile["columns_valid"]:
        synthaml_warnings.append("synthetic_alerts.csv does not match the configured alert schema.")
    if not synthaml_transactions_profile["exists"]:
        synthaml_warnings.append("Companion synthetic_transactions.csv is missing; alerts cannot be joined to transaction flows.")
    elif not synthaml_transactions_profile["parsed"]:
        synthaml_warnings.append("Companion transaction file could not be parsed.")
    datasets.append(DataQualityDatasetItem(
        dataset_name="SynthAML",
        category="Synthetic AML alerts and transactions",
        status="SCHEMA_VALIDATED" if synthaml_valid else ("ORPHAN_ALERTS" if alerts_profile["exists"] and not synthaml_transactions_profile["exists"] else ("NOT_INSTALLED" if synthaml_present == 0 else "PARTIAL_OR_INVALID")),
        file_count=synthaml_present,
        total_rows=int(alerts_profile["rows"]) if alerts_profile["exists"] else 0,
        columns_valid=bool(alerts_profile["parsed"] and alerts_profile["columns_valid"]),
        warnings=synthaml_warnings,
        notes="Alert count comes from the local alerts CSV. Missing transaction records are never fabricated.",
    ))

    amlnet_path = RAW_DIR / "AMLNet_August 2025.csv"
    amlnet_profile = _profile_csv(amlnet_path, AMLNET_COLUMNS)
    amlnet_valid = bool(amlnet_profile["exists"] and amlnet_profile["parsed"] and amlnet_profile["columns_valid"])
    amlnet_warnings = []
    if not amlnet_profile["exists"]:
        amlnet_warnings.append("AMLNet CSV is not present.")
    elif not amlnet_profile["parsed"]:
        amlnet_warnings.append("AMLNet CSV could not be parsed.")
    elif not amlnet_profile["columns_valid"]:
        missing = sorted(set(AMLNET_COLUMNS) - set(amlnet_profile["columns"]))
        amlnet_warnings.append("Configured AMLNet schema mismatch; missing columns: " + (", ".join(missing) if missing else "unexpected column count") + ".")
    datasets.append(DataQualityDatasetItem(
        dataset_name="AMLNet CSV",
        category="External AML benchmark",
        status="SCHEMA_VALIDATED" if amlnet_valid else ("NOT_INSTALLED" if not amlnet_profile["exists"] else "SCHEMA_MISMATCH"),
        file_count=int(amlnet_profile["exists"]),
        total_rows=int(amlnet_profile["rows"]),
        columns_valid=amlnet_valid,
        warnings=amlnet_warnings,
        notes="Row count and columns are read from the local file; this dataset is not merged into the operational ledger.",
    ))

    creditcard_path = RAW_DIR / "creditcard.csv"
    creditcard_profile = _profile_csv(
        creditcard_path,
        FEATURE_NAMES + [TARGET_NAME],
        target_column=TARGET_NAME,
    )
    class_counts = creditcard_profile["target_counts"]
    fraud_count = int(float(class_counts.get("1", 0)))
    non_fraud_count = int(float(class_counts.get("0", 0)))
    creditcard_valid = bool(
        creditcard_profile["exists"] and creditcard_profile["parsed"] and creditcard_profile["columns_valid"]
        and fraud_count + non_fraud_count == int(creditcard_profile["rows"])
    )
    creditcard_warnings = []
    if not creditcard_profile["exists"]:
        creditcard_warnings.append("creditcard.csv is not present at data/raw/creditcard.csv.")
    elif not creditcard_valid:
        creditcard_warnings.append("CSV failed feature/label validation or contains unexpected label values.")
    creditcard_warnings.append("Historical credit-card benchmark with PCA features; not an Indian bank AML dataset.")
    creditcard_notes = (
        "Observed rows: " + format(int(creditcard_profile["rows"]), ",")
        + "; labelled fraud: " + format(fraud_count, ",")
        + "; non-fraud: " + format(non_fraud_count, ",") + "."
        if creditcard_profile["exists"] and creditcard_profile["parsed"]
        else "Expected fields are Time, V1-V28, Amount and Class."
    )
    datasets.append(DataQualityDatasetItem(
        dataset_name="European Credit Card Fraud",
        category="Historical card-fraud benchmark",
        status="SCHEMA_VALIDATED" if creditcard_valid else ("NOT_INSTALLED" if not creditcard_profile["exists"] else "SCHEMA_MISMATCH"),
        file_count=int(creditcard_profile["exists"]),
        total_rows=int(creditcard_profile["rows"]),
        columns_valid=creditcard_valid,
        warnings=creditcard_warnings,
        notes=creditcard_notes,
    ))

    ledger_valid = False
    if ledger_present == 3 and ledger_schema_valid:
        try:
            ledger_valid = bool(get_ledger_data()["validation_report"].is_valid)
        except Exception:
            ledger_valid = False
            ledger_warnings.append("Ledger reconstruction or semantic validation failed.")
            datasets[0] = datasets[0].model_copy(update={
                "warnings": ledger_warnings,
                "status": "VALIDATION_FAILED",
                "columns_valid": False,
            })

    return DataQualityResponse(
        datasets=datasets,
        overall_status="HEALTHY" if ledger_valid else "DEGRADED",
        ledger_conservation_valid=ledger_valid,
    )


# ==============================================================================
# 9. Machine Learning Classifier Endpoints
# ==============================================================================

# Primary ML Model: Interpretable Mule-vs-Bystander Detector (Trained on simulated banking data)
@app.get("/api/ml/mule-detector/status")
def get_mule_detector_status(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return status and summary metrics of the primary interpretable mule-vs-bystander model."""
    from ml.mule_service import MuleDetectorService
    service = MuleDetectorService.get_instance()
    return service.get_status()


@app.get("/api/ml/mule-detector/model-card")
def get_mule_detector_model_card(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the complete model card for the mule detector, including attack family splits and sanity checks."""
    from ml.mule_service import MuleDetectorService
    service = MuleDetectorService.get_instance()
    card = service.get_model_card()
    if "error" in card:
        raise HTTPException(status_code=503, detail=card["error"])
    return card


class MulePredictAccountRequest(BaseModel):
    account_id: str
    case_id: Optional[str] = ""


@app.post("/api/ml/mule-detector/predict")
def predict_account_mule_suspicion(
    request: MulePredictAccountRequest,
    auth: AuthContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Predict mule suspicion and standardized reason codes for an account in the ledger."""
    from ml.mule_service import MuleDetectorService
    service = MuleDetectorService.get_instance()
    data = get_ledger_data()
    pred = service.predict_account(
        account_id=request.account_id,
        case_id=request.case_id or "",
        transactions=data["transactions_df"],
        accounts=data["accounts_df"],
    )
    return pred.to_dict()


# Optional External Benchmark: European Credit Card Fraud Detection (Kaggle / ULB)
@app.get("/api/ml/status")
def get_ml_status(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return optional external benchmark status (European Credit Card Fraud)."""
    service = MLService.get_instance()
    status = service.get_status()
    status["benchmark_role"] = (
        "Optional External Benchmark: European Credit Card Fraud Detection (Kaggle / ULB). "
        "Not used in the main account investigation flow."
    )
    status["primary_mule_model_status_endpoint"] = "/api/ml/mule-detector/status"
    return status


@app.get("/api/ml/evaluation")
def get_ml_evaluation(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return held-out test evaluation report comparing Random Forest and Baseline LR."""
    service = MLService.get_instance()
    try:
        return service.get_evaluation_report()
    except ModelArtifactError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/ml/demo-samples")
def get_ml_demo_samples(auth: AuthContext = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Return verified real test samples for interactive UI prediction demos."""
    service = MLService.get_instance()
    return service.get_demo_samples()


@app.post("/api/ml/predict", response_model=PredictResponse)
def predict_fraud(
    request: PredictRequest,
    auth: AuthContext = Depends(get_current_user),
    _rate: None = Depends(rate_limit("ml_predict", max_requests=40, window_seconds=60)),
) -> PredictResponse:
    """Evaluate fraud risk score for a 30-dimensional feature vector.
    
    Validates exact feature names (Time, V1..V28, Amount) and numeric types.
    Does NOT modify financial tracing or Consensus Lien calculations.
    """
    # Validate the feature contract before checking whether a trained artifact is available.
    # Malformed requests should remain 422 errors even when the model is not installed.
    provided_features = set(request.features)
    missing_features = sorted(set(FEATURE_NAMES) - provided_features)
    extra_features = sorted(provided_features - set(FEATURE_NAMES))
    if missing_features:
        raise HTTPException(status_code=422, detail=f"Missing required feature(s): {missing_features}")
    if extra_features:
        raise HTTPException(status_code=422, detail=f"Unexpected extra feature(s) provided: {extra_features}")

    service = MLService.get_instance()
    try:
        return service.predict(request.features)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ModelArtifactError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ==============================================================================
# Attack Lab Adversarial Simulation Endpoints
# ==============================================================================

_ATTACKLAB_CACHE: Dict[Tuple[int, int, int], Dict[str, Any]] = {}

@app.get("/api/attacklab/run")
def run_attacklab_experiment(
    seed: int = Query(42, description="Deterministic random seed"),
    population: int = Query(24, ge=5, le=50, description="Population size (20-40 recommended)"),
    generations: int = Query(15, ge=2, le=40, description="Generations count (15-30 recommended)"),
    auth: AuthContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run seeded evolutionary attacker search and cross-family defense evaluation."""
    cache_key = (seed, population, generations)
    if cache_key in _ATTACKLAB_CACHE:
        return _ATTACKLAB_CACHE[cache_key]

    from attacklab.policy_tuning import AttackLabEngine
    engine = AttackLabEngine()
    report = engine.run_full_experiment(
        seed=seed,
        population_size=population,
        generations=generations,
    )
    result = report.to_dict()
    _ATTACKLAB_CACHE[cache_key] = result
    return result


# ==============================================================================
# 10. TraceProof Multi-Rail Evidence Reconstruction Endpoints
# ==============================================================================

@app.get("/api/traceproof/scenarios")
def get_traceproof_scenarios(auth: AuthContext = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Return only simulated scenarios whose case scope is authorized for this identity."""
    return [
        scenario
        for scenario in get_scenario_metadata_list()
        if auth.can_access_case(str(scenario.get("case_id", "")))
    ]


@app.post("/api/traceproof/start", response_model=TraceProofResponse)
def start_traceproof(
    req: StartTraceRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
    _rate: None = Depends(rate_limit("traceproof", max_requests=30, window_seconds=60)),
) -> TraceProofResponse:
    """Execute a cryptographic multi-rail evidence reconstruction trace with BOLA enforcement."""
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(req.case_id, auth, endpoint=request.url.path, method="POST", client_ip=client_ip)

    coordinator = TraceCoordinator.get_instance()
    try:
        return coordinator.execute_trace(
            case_id=req.case_id,
            seed_reference=req.seed_reference,
            scenario_id=req.scenario_id,
            max_hops=req.max_hops,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TraceProof coordinator failure: {str(e)}")


@app.get("/api/traceproof/requests/{request_id}", response_model=TraceProofResponse)
def get_traceproof_result(
    request_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> TraceProofResponse:
    """Retrieve the results and evidence graph for a specific trace request ID."""
    coordinator = TraceCoordinator.get_instance()
    res = coordinator.get_trace(request_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Trace request '{request_id}' not found.")
    client_ip = "unknown"
    case_id = getattr(res, "case_id", None)
    if not case_id:
        raise HTTPException(status_code=403, detail="Trace result has no verifiable case scope.")
    check_case_access(case_id, auth, endpoint="/api/traceproof/requests/" + request_id, method="GET", client_ip=client_ip)
    return res


@app.post("/api/traceproof/verify-envelope", response_model=EnvelopeVerificationResult)
def verify_envelope(
    req: VerifyEnvelopeRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
) -> EnvelopeVerificationResult:
    """Verify an attestation; enforce case authorization when its trace is stored locally.

    Standalone verification accepts a self-contained envelope that is not in this process's
    trace cache. It returns only cryptographic verification information about the submitted
    envelope, not stored transaction records. If a local trace exists, case scope is enforced.
    """
    coordinator = TraceCoordinator.get_instance()
    trace = coordinator.get_trace(req.envelope.trace_request_id)
    client_ip = request.client.host if request.client else "unknown"
    if trace:
        check_case_access(trace.case_id, auth, endpoint=request.url.path, method="POST", client_ip=client_ip)

    key_manager = InstitutionKeyManager.get_instance()
    return key_manager.verify_envelope(req.envelope)


@app.get("/api/v1/federated/compare/{case_id}", response_model=FederatedComparisonResponse)
@app.get("/api/federated/compare/{case_id}", response_model=FederatedComparisonResponse)
def compare_federated_vs_centralized(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
    simulate_missing: bool = Query(False, description="Simulate missing passports in transit"),
    simulate_tamper: bool = Query(False, description="Simulate tampered passports"),
    simulate_replay: bool = Query(False, description="Simulate passport replay attacks"),
    simulate_expired: bool = Query(False, description="Simulate expired passports"),
    simulate_wrong_key: bool = Query(False, description="Simulate unauthorized signature"),
) -> FederatedComparisonResponse:
    """Returns side-by-side comparison between federated multi-rail and centralized fund tracing.

    Partitions accounts across 3 banks plus one wallet rail. For each cross-institution hop,
    a signed Passport carries evidence with per-method segments. Demonstrates mathematical
    equivalence under verified conditions and evidence-bounded range widening under unverified conditions.
    """
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    cases_df = data["cases_df"]
    txs_df = data["transactions_df"]
    accs_df = data["accounts_df"]

    matched = cases_df[cases_df["case_id"] == case_id]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    case_txs = txs_df[txs_df["case_id"] == case_id]
    if case_txs.empty:
        raise HTTPException(status_code=400, detail=f"No transactions linked to case '{case_id}'.")

    origin_tx = select_case_source_transaction(case_txs)
    if origin_tx is None:
        raise HTTPException(status_code=400, detail=f"No source transaction is available for case '{case_id}'.")

    fault_missing = set(case_txs["transaction_id"]) if simulate_missing else None
    fault_tamper = set(case_txs["transaction_id"]) if simulate_tamper else None
    fault_replay = set(case_txs["transaction_id"]) if simulate_replay else None
    fault_expire = set(case_txs["transaction_id"]) if simulate_expired else None
    fault_wrong_key = set(case_txs["transaction_id"]) if simulate_wrong_key else None

    coordinator = FederatedCoordinator()
    res = coordinator.run_trace(
        accounts=accs_df,
        transactions=txs_df,
        source_transaction_id=str(origin_tx["transaction_id"]),
        case_id=case_id,
        fault_missing_transfers=fault_missing,
        fault_tamper_transfers=fault_tamper,
        fault_expire_transfers=fault_expire,
        fault_replay_transfers=fault_replay,
        fault_wrong_key_transfers=fault_wrong_key,
    )
    return res


# ==============================================================================
# 11. Security Governance & Administrative Endpoints
# ==============================================================================

@app.get("/api/admin/audit-logs", response_model=List[SecurityAuditEvent])
def get_audit_logs(
    severity: Optional[AuditSeverity] = None,
    event_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(require_role(Role.COMPLIANCE_ADMIN, Role.AUDITOR)),
) -> List[SecurityAuditEvent]:
    """Retrieve security audit events. Requires COMPLIANCE_ADMIN or AUDITOR role."""
    audit = SecurityAuditLogger.get_instance()
    return audit.get_events(limit=limit, severity=severity, event_type=event_type)


@app.get("/api/admin/security-status", response_model=SecurityStatusResponse)
def get_security_status(
    auth: AuthContext = Depends(require_role(Role.COMPLIANCE_ADMIN)),
) -> SecurityStatusResponse:
    """Return real-time security posture and defense telemetry. Requires COMPLIANCE_ADMIN role."""
    audit = SecurityAuditLogger.get_instance()
    telemetry = audit.get_telemetry()
    ml_service = MLService.get_instance()
    key_manager = InstitutionKeyManager.get_instance()

    demo_mode = DEMO_AUTH_ENABLED
    registered_keys = len(key_manager._public_registry)
    return SecurityStatusResponse(
        status="LOCAL_DEMO_ONLY" if demo_mode else "PRODUCTION_AUTH_NOT_CONFIGURED",
        auth_mode="LOCAL_DEMO_TOKEN (NOT PRODUCTION AUTH)" if demo_mode else "UNCONFIGURED",
        production_auth_ready=False,
        demo_auth_enabled=demo_mode,
        pki_signature_algorithm=("Ed25519; trusted keys registered" if registered_keys else "Ed25519; no trusted institution keys registered"),
        model_sha256_verified=ml_service.artifact_sha256_verified,
        case_scope_authorization_status="CASE_SCOPED_CHECKS_IMPLEMENTED_NOT_INDEPENDENTLY_VERIFIED",
        rate_limiting_active=True,
        rate_limiting_scope="Per-IP route limits on ML prediction and TraceProof start; not a global gateway limit",
        hidden_data_isolation_status="Operational modules are separated from evaluation ground truth by design; this is not a penetration-test result",
        total_audit_events=telemetry["total_events"],
        security_denials_count=telemetry["denials_count"],
        active_institutions_registered=registered_keys,
    )


@app.post("/api/admin/audit/verify-chain", response_model=ChainVerificationResponse)
@app.get("/api/admin/audit/verify-chain", response_model=ChainVerificationResponse)
def verify_audit_chain(
    auth: AuthContext = Depends(require_role(Role.COMPLIANCE_ADMIN, Role.AUDITOR)),
) -> ChainVerificationResponse:
    """Verify cryptographic SHA-256 hash-chain integrity of the security audit log from genesis."""
    audit = SecurityAuditLogger.get_instance()
    res = audit.verify_chain()
    return ChainVerificationResponse(**res)


@app.get("/api/receipts/{receipt_id}")
def get_receipt_by_id(
    receipt_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve canonical signed JSON receipt for offline verification with python -m verifier."""
    receipt = ReceiptRegistry.get_instance().get(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail=f"Receipt '{receipt_id}' not found.")
    if not auth.can_access_case(str(receipt.get("case_id", ""))):
        raise HTTPException(status_code=403, detail="Not authorized to access receipt for this case.")
    return receipt


@app.get("/api/cases/{case_id}/receipts")
def list_case_receipts(
    case_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List all cryptographic hold receipts generated for a case."""
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)
    return ReceiptRegistry.get_instance().list_by_case(case_id)

