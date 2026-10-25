"""Smart-Freeze Decision Support Engine.

Recommends calibrated actions per account using transparent harm signals,
Consensus Lien core and margin bounds, joint feasibility caps, and rigorous safeguards.

Action Ladder:
1. none: Tracking only, no hold.
2. lien_core: Lien on consensus core only (minimum across all methods).
3. lien_core_plus_margin: Lien on core + time-boxed margin hold on the margin.
4. outflow_cap: Cap on outgoing debit transfers rather than a full freeze.
5. account_level_hold: Full account freeze (strictly requires human analyst approval).

Safeguards:
- Harm signals and evidence can ONLY reduce the MARGIN, never the core.
- Uploaded documents never release anything alone (require human analyst review).
- Accounts below configurable de-minimis total stolen amount get tracking, not a hold.
- If core is 0, margin is large, and mule score is high, recommend time-boxed margin hold needing approval.
- Joint feasible upper cap is strictly conserved.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from engine.consensus_lien import ConsensusLienEngine, ConsensusLienResult


CONFIG_FILE_PATH = Path(__file__).resolve().parent / "decision_policy.json"

RECOMMENDATION_DISCLAIMER = (
    "RECOMMEND-ONLY DECISION SUPPORT — All actions shown are recommendations generated "
    "by policy rules and consensus fund-tracing models. No automated account freezes or "
    "fund releases are executed. Every consequential hold requires authorized human analyst review."
)


class DecisionAction(str, Enum):
    """Calibrated action ladder for account decision support."""
    NONE = "none"
    LIEN_CORE = "lien_core"
    LIEN_CORE_PLUS_MARGIN = "lien_core_plus_margin"
    OUTFLOW_CAP = "outflow_cap"
    ACCOUNT_LEVEL_HOLD = "account_level_hold"


@dataclass(frozen=True)
class PolicyConfig:
    """Configurable policy thresholds loaded from versioned config."""
    name: str
    display_name: str
    description: str
    de_minimis_total_paise: int
    harm_reduction_factor: float
    mule_score_threshold: float
    large_margin_threshold_paise: int
    margin_hold_duration_hours: int
    allow_automatic_margin_hold: bool
    outflow_cap_daily_paise: int


@dataclass
class AccountRecommendation:
    """Per-account recommendation output adhering strictly to the contract."""
    account_id: str
    core: int  # min across methods (paise)
    margin: int  # max - min, within joint cap (paise)
    free: int  # available balance after action (paise)
    action: str  # one of DecisionAction values
    reasons: List[str]  # structured reasons with reason codes
    policy_version: str  # version string
    requires_human_approval: bool  # True if analyst approval is required

    # Supplementary decision context
    harm_score: float = 0.0
    mule_score: float = 0.0
    current_balance_paise: int = 0
    held_core_paise: int = 0
    held_margin_paise: int = 0
    effective_lien_paise: int = 0
    margin_hold_duration_hours: Optional[int] = None
    receipt_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CaseRecommendationsResult:
    """Complete case-level recommendations report."""
    case_id: str
    policy_name: str
    policy_version: str
    stolen_amount_paise: int
    joint_cap_paise: int
    recommendations: List[AccountRecommendation]
    total_core_paise: int
    total_margin_paise: int
    total_held_paise: int
    requires_human_approval_count: int
    governance_notice: str = RECOMMENDATION_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    """Calculates explainable, safeguard-guaranteed action recommendations."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE_PATH
        self.raw_config = self._load_raw_config()
        self.version = self.raw_config.get("version", "1.0.0")

    def _load_raw_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {
                "version": "1.0.0",
                "default_policy": "balanced",
                "policies": {
                    "balanced": {
                        "name": "balanced",
                        "display_name": "Balanced (Prudent Standard)",
                        "description": "Standard balanced decision policy",
                        "de_minimis_total_paise": 200000,
                        "harm_reduction_factor": 0.6,
                        "mule_score_threshold": 60.0,
                        "large_margin_threshold_paise": 100000,
                        "margin_hold_duration_hours": 48,
                        "allow_automatic_margin_hold": true,
                        "outflow_cap_daily_paise": 500000,
                    }
                },
            }
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_policy(self, policy_name: str = "balanced") -> PolicyConfig:
        """Retrieve policy configuration by name with fallback to default."""
        policies = self.raw_config.get("policies", {})
        p_dict = policies.get(policy_name) or policies.get("balanced")
        if not p_dict:
            raise KeyError(f"Policy '{policy_name}' not defined in config.")

        return PolicyConfig(
            name=p_dict["name"],
            display_name=p_dict.get("display_name", p_dict["name"]),
            description=p_dict.get("description", ""),
            de_minimis_total_paise=int(p_dict.get("de_minimis_total_paise", 200_000)),
            harm_reduction_factor=float(p_dict.get("harm_reduction_factor", 0.6)),
            mule_score_threshold=float(p_dict.get("mule_score_threshold", 60.0)),
            large_margin_threshold_paise=int(p_dict.get("large_margin_threshold_paise", 100_000)),
            margin_hold_duration_hours=int(p_dict.get("margin_hold_duration_hours", 48)),
            allow_automatic_margin_hold=bool(p_dict.get("allow_automatic_margin_hold", True)),
            outflow_cap_daily_paise=int(p_dict.get("outflow_cap_daily_paise", 500_000)),
        )

    @staticmethod
    def compute_harm_score(
        account_id: str,
        current_balance: int,
        upper_suspected: int,
        transactions: List[Dict[str, Any]],
        account_meta: Dict[str, Any],
    ) -> Tuple[float, List[str]]:
        """Compute transparent, explainable harm score with documented reason codes."""
        score = 0.0
        reasons: List[str] = []

        # 1. Clean Balance Share (up to 0.40)
        if current_balance > 0:
            clean_balance = max(0, current_balance - upper_suspected)
            clean_share = clean_balance / current_balance
            if clean_share > 0.50:
                clean_pts = clean_share * 0.40
                score += clean_pts
                reasons.append(
                    f"HARM_CLEAN_MAJORITY: Predominantly clean funds ({clean_share * 100:.1f}% clean balance)."
                )

        # 2. Salary-like credits (0.30)
        has_salary = False
        for t in transactions:
            if t.get("to_account") == account_id and t.get("transaction_type") == "salary_credit":
                has_salary = True
                break
        if not has_salary and account_meta.get("account_type") in ("salary", "salaried"):
            has_salary = True

        if has_salary:
            score += 0.30
            reasons.append("HARM_SALARY_INCOME: Regular payroll / salary credits detected; severe livelihood impact.")

        # 3. Merchant daily inflow (0.20)
        is_merchant = (
            account_meta.get("account_type") == "merchant"
            or any(t.get("to_account") == account_id and t.get("transaction_type") == "merchant_payment" for t in transactions)
        )
        if is_merchant:
            score += 0.20
            reasons.append("HARM_MERCHANT_COMMERCE: Active commercial merchant operations; business payroll/working capital impact.")

        # 4. Scheduled debits (0.10)
        has_scheduled = any(
            t.get("from_account") == account_id and t.get("transaction_type") in ("bill_payment", "utility", "fee")
            for t in transactions
        )
        if has_scheduled:
            score += 0.10
            reasons.append("HARM_SCHEDULED_DEBITS: Recurring obligations / scheduled debits detected.")

        final_harm = min(1.0, max(0.0, score))
        return final_harm, reasons

    def evaluate_account(
        self,
        account_id: str,
        current_balance: int,
        core_paise: int,
        margin_paise: int,
        harm_score: float,
        harm_reasons: List[str],
        mule_score: float,
        policy: PolicyConfig,
        uploaded_documents: Optional[List[Dict[str, Any]]] = None,
        override_de_minimis: Optional[int] = None,
    ) -> AccountRecommendation:
        """Evaluate a single account and produce a safeguard-guaranteed recommendation."""
        reasons: List[str] = []
        requires_human_approval = False

        de_minimis_limit = (
            override_de_minimis if override_de_minimis is not None else policy.de_minimis_total_paise
        )

        total_stolen = core_paise + margin_paise

        # -------------------------------------------------------------
        # Safeguard 1: De-minimis Threshold Applied to Total Stolen
        # -------------------------------------------------------------
        if total_stolen < de_minimis_limit:
            action = DecisionAction.NONE.value
            held_core = 0
            held_margin = 0
            reasons.append(
                f"DE_MINIMIS_TRACKING_ONLY: Total suspected stolen amount (₹{total_stolen / 100:,.2f}) "
                f"is below de-minimis threshold (₹{de_minimis_limit / 100:,.2f}); tracking only, no hold placed."
            )
        else:
            # ---------------------------------------------------------
            # Safeguard 2: Core is NEVER reduced by harm signals
            # ---------------------------------------------------------
            held_core = core_paise
            if held_core > 0:
                reasons.append(
                    f"CORE_CONSENSUS_LIEN: Consensus core of ₹{held_core / 100:,.2f} agreed by all independent tracing methods."
                )

            # ---------------------------------------------------------
            # Safeguard 3: Harm signals can ONLY reduce the MARGIN
            # ---------------------------------------------------------
            margin_discount = 0
            if margin_paise > 0 and harm_score > 0:
                discount_rate = policy.harm_reduction_factor * harm_score
                margin_discount = min(margin_paise, int(margin_paise * discount_rate))
                if margin_discount > 0:
                    reasons.append(
                        f"MARGIN_DISCOUNTED_BY_HARM: Margin hold discounted by ₹{margin_discount / 100:,.2f} "
                        f"({discount_rate * 100:.1f}% reduction) due to verified harm signals."
                    )
                    reasons.extend(harm_reasons)

            held_margin = max(0, margin_paise - margin_discount)

            # ---------------------------------------------------------
            # Safeguard 4: Core is 0, margin is large, mule score high
            # ---------------------------------------------------------
            is_mule_spike = (
                core_paise == 0
                and margin_paise >= policy.large_margin_threshold_paise
                and mule_score >= policy.mule_score_threshold
            )

            if is_mule_spike:
                action = DecisionAction.LIEN_CORE_PLUS_MARGIN.value
                held_margin = margin_paise  # Preserved full margin for investigation
                requires_human_approval = True
                reasons.append(
                    f"HIGH_MULE_RISK_MARGIN_HOLD: Core is ₹0 but margin is large (₹{margin_paise / 100:,.2f}) "
                    f"and mule score is high ({mule_score:.1f}); recommending time-boxed margin hold needing approval."
                )

            # Severe mule pattern with negligible clean funds
            elif mule_score >= 85.0 and core_paise > 0 and current_balance > 0 and (current_balance - total_stolen) / current_balance < 0.10:
                action = DecisionAction.ACCOUNT_LEVEL_HOLD.value
                requires_human_approval = True
                reasons.append(
                    f"ACCOUNT_LEVEL_HOLD_ANALYST_REQ: Critical mule indicator ({mule_score:.1f}) with negligible clean funds; "
                    "account-level hold recommended, strictly requires human analyst review."
                )

            elif held_margin > 0:
                action = DecisionAction.LIEN_CORE_PLUS_MARGIN.value
                reasons.append(
                    f"MARGIN_HOLD_RECOMMENDED: Time-boxed hold of ₹{held_margin / 100:,.2f} placed on disputed margin."
                )
                if not policy.allow_automatic_margin_hold:
                    requires_human_approval = True

            elif held_core > 0:
                action = DecisionAction.LIEN_CORE.value
                requires_human_approval = False

            else:
                action = DecisionAction.NONE.value
                reasons.append("NO_HOLD_RECOMMENDED: Disputed funds fully discounted by harm mitigation rules.")

        # -------------------------------------------------------------
        # Safeguard 5: Uploaded documents NEVER release anything alone
        # -------------------------------------------------------------
        if uploaded_documents and len(uploaded_documents) > 0:
            requires_human_approval = True
            reasons.append(
                f"DOC_SUBMITTED_REQUIRES_ANALYST: {len(uploaded_documents)} document(s) uploaded by account holder; "
                "cannot automatically release funds without human review."
            )

        # Free funds calculation
        effective_lien = min(current_balance, held_core + held_margin)
        free_paise = max(0, current_balance - effective_lien)

        duration_hours = policy.margin_hold_duration_hours if held_margin > 0 else None

        return AccountRecommendation(
            account_id=account_id,
            core=core_paise,
            margin=margin_paise,
            free=free_paise,
            action=action,
            reasons=reasons,
            policy_version=self.version,
            requires_human_approval=requires_human_approval,
            harm_score=round(harm_score, 4),
            mule_score=round(mule_score, 2),
            current_balance_paise=current_balance,
            held_core_paise=held_core,
            held_margin_paise=held_margin,
            effective_lien_paise=effective_lien,
            margin_hold_duration_hours=duration_hours,
        )

    def evaluate_case(
        self,
        case_id: str,
        accounts: List[Dict[str, Any]] | pd.DataFrame,
        transactions: List[Dict[str, Any]] | pd.DataFrame,
        source_transaction_id: str,
        policy_name: str = "balanced",
        mule_scores: Optional[Dict[str, float]] = None,
        uploaded_documents_by_acc: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        override_de_minimis: Optional[int] = None,
    ) -> CaseRecommendationsResult:
        """Run full Consensus Lien and produce case recommendations."""
        policy = self.get_policy(policy_name)
        mule_reasons_map: Dict[str, List[str]] = {}
        if mule_scores is not None:
            mule_map = dict(mule_scores)
        else:
            try:
                from ml.mule_service import MuleDetectorService
                mule_service = MuleDetectorService.get_instance()
                preds = mule_service.predict_case_accounts(
                    case_id=case_id,
                    transactions=transactions,
                    accounts=accounts,
                )
                mule_map = {aid: p.mule_score for aid, p in preds.items()}
                mule_reasons_map = {aid: p.reason_codes for aid, p in preds.items()}
            except Exception:
                mule_map = {}
                mule_reasons_map = {}

        docs_map = uploaded_documents_by_acc or {}

        acc_list = (
            accounts.to_dict(orient="records")
            if isinstance(accounts, pd.DataFrame)
            else list(accounts)
        )
        tx_list = (
            transactions.to_dict(orient="records")
            if isinstance(transactions, pd.DataFrame)
            else list(transactions)
        )

        acc_meta = {str(a["account_id"]): a for a in acc_list}

        # 1. Run Consensus Lien across all methods
        lien_result: ConsensusLienResult = ConsensusLienEngine.run_all_methods(
            accounts=acc_list,
            transactions=tx_list,
            source_transaction_id=source_transaction_id,
            source_case_id=case_id,
        )

        joint_cap = lien_result.joint_feasible_upper_paise
        stolen_amt = lien_result.initial_suspected_amount_paise

        # Current balances from transactions or metadata
        sim_balances: Dict[str, int] = {str(a["account_id"]): int(a["opening_balance_paise"]) for a in acc_list}
        for t in sorted(tx_list, key=lambda x: str(x.get("timestamp", ""))):
            fa = str(t.get("from_account", ""))
            ta = str(t.get("to_account", ""))
            amt = int(t.get("amount_paise", 0))
            if not fa.startswith("EXT_") and fa in sim_balances:
                sim_balances[fa] -= amt
            if not ta.startswith("EXT_") and ta in sim_balances:
                sim_balances[ta] += amt

        # Scale raw margins within joint cap if sum of upper bounds exceeds cap
        total_raw_core = sum(l.lower_estimate_paise for l in lien_result.account_liens.values())
        rem_cap_for_margin = max(0, joint_cap - total_raw_core)
        sum_raw_margins = sum(l.disagreement_paise for l in lien_result.account_liens.values())

        recommendations: List[AccountRecommendation] = []

        for acc_id, lien in sorted(lien_result.account_liens.items()):
            core = lien.lower_estimate_paise
            raw_margin = lien.disagreement_paise

            # Bound margin within remaining joint cap
            if sum_raw_margins > rem_cap_for_margin and sum_raw_margins > 0:
                scaled_margin = (raw_margin * rem_cap_for_margin) // sum_raw_margins
            else:
                scaled_margin = raw_margin

            bal = sim_balances.get(acc_id, 0)
            harm, harm_reasons = self.compute_harm_score(
                account_id=acc_id,
                current_balance=bal,
                upper_suspected=core + scaled_margin,
                transactions=tx_list,
                account_meta=acc_meta.get(acc_id, {}),
            )

            mule_score = mule_map.get(acc_id, 0.0)
            docs = docs_map.get(acc_id, [])

            rec = self.evaluate_account(
                account_id=acc_id,
                current_balance=bal,
                core_paise=core,
                margin_paise=scaled_margin,
                harm_score=harm,
                harm_reasons=harm_reasons,
                mule_score=mule_score,
                policy=policy,
                uploaded_documents=docs,
                override_de_minimis=override_de_minimis,
            )
            for rc in mule_reasons_map.get(acc_id, []):
                if rc not in rec.reasons:
                    rec.reasons.append(rc)
            recommendations.append(rec)

        # Aggregate totals
        tot_core = sum(r.held_core_paise for r in recommendations)
        tot_margin = sum(r.held_margin_paise for r in recommendations)
        tot_held = sum(r.effective_lien_paise for r in recommendations)
        approval_count = sum(1 for r in recommendations if r.requires_human_approval)

        return CaseRecommendationsResult(
            case_id=case_id,
            policy_name=policy.name,
            policy_version=self.version,
            stolen_amount_paise=stolen_amt,
            joint_cap_paise=joint_cap,
            recommendations=recommendations,
            total_core_paise=tot_core,
            total_margin_paise=tot_margin,
            total_held_paise=tot_held,
            requires_human_approval_count=approval_count,
        )
