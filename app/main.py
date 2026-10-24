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
from security.models import (
    Role,
    AuthContext,
    SecurityAuditEvent,
    SecurityStatusResponse,
    AuditSeverity,
)
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


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_nodes: int
    total_edges: int


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
    account_liens: List[AccountLienItem]
    method_details: Dict[str, Any]
    explanation: Dict[str, Any]
    governance_notice: str


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


@app.get("/api/auth/personas")
def get_auth_personas() -> Dict[str, Any]:
    """Return safe local demo persona metadata only; never return bearer tokens."""
    if not DEMO_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Local demonstration identities are disabled.")
    return {
        "mode": "LOCAL_DEMO_ONLY",
        "personas": [
            {
                "persona_id": user.user_id,
                "display_name": user.display_name,
                "role": user.role.value,
                "assigned_case_count": len(user.assigned_cases),
                "institution_id": user.institution_id,
            }
            for user in DEMO_PERSONAS.values()
        ],
    }


class DemoSessionRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, max_length=100)


@app.post("/api/auth/demo-session")
def create_demo_session(req: DemoSessionRequest) -> Dict[str, Any]:
    """Issue a random, short-lived bearer token only for isolated local demonstration mode."""
    if not DEMO_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Local demonstration identities are disabled.")
    for user in DEMO_PERSONAS.values():
        if user.user_id == req.persona_id:
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
                "warning": "This is a short-lived mock identity for local testing, not production authentication.",
            }
    raise HTTPException(status_code=404, detail="Unknown demonstration persona.")


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
    return {"status": "healthy", "service": "fairhold-api", "version": app.version}


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
        origin_tx = case_txs.iloc[0]["transaction_id"] if not case_txs.empty else None

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
    origin_tx = case_txs.iloc[0]["transaction_id"] if not case_txs.empty else None

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
    """Returns nodes and directed edges formatted for Cytoscape.js or web visualizations."""
    client_ip = request.client.host if request.client else "unknown"
    if case_id:
        check_case_access(case_id, auth, endpoint=request.url.path, method="GET", client_ip=client_ip)

    data = get_ledger_data()
    accs_df = data["accounts_df"]
    txs_df = data["transactions_df"]
    final_balances = data["final_balances"]

    if case_id:
        filtered_txs = txs_df[txs_df["case_id"] == case_id]
    elif auth.user.role == Role.INVESTIGATOR and "*" not in auth.user.assigned_cases:
        filtered_txs = txs_df[txs_df["case_id"].isin(auth.user.assigned_cases)]
    else:
        filtered_txs = txs_df

    # Identify nodes present in filtered transactions
    involved_acc_ids = set(filtered_txs["from_account"]).union(set(filtered_txs["to_account"]))
    acc_map = {str(r["account_id"]): r for _, r in accs_df.iterrows()}

    nodes: List[GraphNode] = []
    for aid in sorted(list(involved_acc_ids)):
        is_ext = aid.startswith(EXTERNAL_ACCOUNT_PREFIX)
        opening = None
        final = None
        hist_comp = None
        if aid in acc_map:
            acc_info = acc_map[aid]
            acc_type = str(acc_info["account_type"])
            if auth.user.role != Role.INVESTIGATOR:
                opening = int(acc_info["opening_balance_paise"])
                final = int(final_balances.get(aid, opening))
                hist_comp = bool(acc_info["history_complete"])
            else:
                related = txs_df[(txs_df["from_account"] == aid) | (txs_df["to_account"] == aid)]
                related_case_ids = set(related["case_id"].fillna("").astype(str).str.strip())
                allowed_scope = {case_id} if case_id else set(auth.user.assigned_cases)
                # Account-wide balances are hidden if they include events outside the current authorized scope.
                if related_case_ids and "" not in related_case_ids and related_case_ids.issubset(allowed_scope):
                    opening = int(acc_info["opening_balance_paise"])
                    final = int(final_balances.get(aid, opening))
                    hist_comp = bool(acc_info["history_complete"])
        else:
            # External counterparties have no verified account-level balance in this ledger.
            acc_type = "external"

        nodes.append(
            GraphNode(
                id=aid,
                label=aid,
                type=acc_type,
                is_external=is_ext,
                opening_balance_inr=(opening / 100.0) if opening is not None else None,
                final_balance_inr=(final / 100.0) if final is not None else None,
                history_complete=hist_comp,
            )
        )

    edges: List[GraphEdge] = []
    for _, tx in filtered_txs.iterrows():
        edges.append(
            GraphEdge(
                id=str(tx["transaction_id"]),
                source=str(tx["from_account"]),
                target=str(tx["to_account"]),
                amount_paise=int(tx["amount_paise"]),
                amount_inr=int(tx["amount_paise"]) / 100.0,
                timestamp=str(tx["timestamp"]),
                transaction_type=str(tx["transaction_type"]),
                case_id=str(tx.get("case_id", "") or ""),
                evidence_status=str(tx.get("evidence_status", "unflagged")),
            )
        )

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
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

    origin_tx = case_txs.iloc[0]
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
            f"total upper bound: ₹{lien_res.total_upper_retained_paise / 100:,.2f}, "
            f"overall disagreement: ₹{lien_res.overall_disagreement_paise / 100:,.2f}."
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

    return ConsensusLienResponse(
        case_id=case_id,
        source_transaction_id=origin_tx_id,
        source_amount_paise=origin_amt,
        source_amount_inr=origin_amt / 100.0,
        consensus_status=lien_res.status,
        total_lower_bound_paise=lien_res.total_lower_retained_paise,
        total_lower_bound_inr=lien_res.total_lower_retained_paise / 100.0,
        total_upper_bound_paise=lien_res.total_upper_retained_paise,
        total_upper_bound_inr=lien_res.total_upper_retained_paise / 100.0,
        total_disagreement_paise=lien_res.overall_disagreement_paise,
        total_disagreement_inr=lien_res.overall_disagreement_paise / 100.0,
        account_liens=account_liens,
        method_details={
            "proportional": {"status": "COMPLETED", "assumption": "Fungible commingling across concurrent balance"},
            "fifo": {"status": "COMPLETED", "assumption": "Oldest source lots consumed first in chronological order"},
            "libr": {"status": "COMPLETED", "assumption": "Clean funds dissipate first with irreversible lowest intermediate balance ceiling"},
        },
        explanation=explanation,
        governance_notice=GOVERNANCE_DISCLAIMER,
    )


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
        dataset_name="FairHold Synthetic Ledger",
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

@app.get("/api/ml/status")
def get_ml_status(auth: AuthContext = Depends(get_current_user)) -> Dict[str, Any]:
    """Return model readiness, artifact version, operating threshold, and feature schema."""
    service = MLService.get_instance()
    return service.get_status()


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
    """Verify an envelope only when its originating trace belongs to an accessible case."""
    coordinator = TraceCoordinator.get_instance()
    trace = coordinator.get_trace(req.envelope.trace_request_id)
    if not trace:
        raise HTTPException(status_code=404, detail="The trace request for this envelope was not found.")
    client_ip = request.client.host if request.client else "unknown"
    check_case_access(trace.case_id, auth, endpoint=request.url.path, method="POST", client_ip=client_ip)
    key_manager = InstitutionKeyManager.get_instance()
    return key_manager.verify_envelope(req.envelope)


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
