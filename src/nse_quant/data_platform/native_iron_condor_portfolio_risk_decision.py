"""Native iron-condor portfolio-risk decision evaluation; observational only.

Evaluates a portfolio-risk stage decision from a native strategy-stage outcome
and portfolio-risk inputs. It never grants eligibility, enables live trading,
heals a coverage gap, or authorizes execution. POINT_IN_TIME_DECISION remains
rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.risk.native_portfolio_risk import (
    PortfolioRiskSettings,
    evaluate_portfolio_risk,
)


@dataclass(frozen=True)
class NativePortfolioRiskDecisionInputBundle:
    coverage_revision_id: str
    coverage_recording_fingerprint: str
    evidence_refs: dict[str, str]
    strategy_outcome: dict[str, Any]
    proposal: dict[str, Any]
    open_positions: list[dict[str, Any]]
    settings: PortfolioRiskSettings


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_native_portfolio_risk_decision_input_bundle(
    bundle: NativePortfolioRiskDecisionInputBundle,
) -> None:
    """Validate exact inputs for the portfolio-risk stage."""
    if type(bundle) is not NativePortfolioRiskDecisionInputBundle:
        raise Rejected("TYPED_NATIVE_PORTFOLIO_RISK_INPUT_BUNDLE_REQUIRED")
    if not _pin(bundle.coverage_revision_id):
        raise Rejected("EXACT_COVERAGE_REVISION_PIN_REQUIRED")
    if not _pin(bundle.coverage_recording_fingerprint):
        raise Rejected("EXACT_COVERAGE_RECORDING_FINGERPRINT_REQUIRED")
    if type(bundle.evidence_refs) is not dict or not bundle.evidence_refs:
        raise Rejected("EXACT_EVIDENCE_REFS_REQUIRED")
    if "authoritative_identity_and_time" in bundle.evidence_refs:
        raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
    if type(bundle.strategy_outcome) is not dict:
        raise Rejected("STRATEGY_OUTCOME_MAPPING_REQUIRED")
    if bundle.strategy_outcome.get("decision_type") == "POINT_IN_TIME_DECISION":
        raise Rejected("POINT_IN_TIME_DECISION_REJECTED")
    if bundle.strategy_outcome.get("decision_type") != "NATIVE_STRATEGY_DECISION":
        raise Rejected("NATIVE_STRATEGY_DECISION_REQUIRED")
    if bundle.strategy_outcome.get("action") not in ("monitor", "no_trade"):
        raise Rejected("UNSUPPORTED_STRATEGY_ACTION")
    if type(bundle.proposal) is not dict:
        raise Rejected("PROPOSAL_MAPPING_REQUIRED")
    if type(bundle.open_positions) is not list:
        raise Rejected("OPEN_POSITIONS_LIST_REQUIRED")
    if type(bundle.settings) is not PortfolioRiskSettings:
        raise Rejected("TYPED_PORTFOLIO_RISK_SETTINGS_REQUIRED")


def evaluate_native_portfolio_risk_decision(
    bundle: NativePortfolioRiskDecisionInputBundle,
) -> dict[str, Any]:
    """Evaluate an observational native portfolio-risk-stage decision."""
    validate_native_portfolio_risk_decision_input_bundle(bundle)

    risk = evaluate_portfolio_risk(
        proposal=bundle.proposal,
        open_positions=bundle.open_positions,
        settings=bundle.settings,
    )
    action = "approve" if risk.approved else "block"
    outcome = {
        "decision_type": "NATIVE_PORTFOLIO_RISK_DECISION",
        "action": action,
        "reasons": list(risk.reasons),
        "checks": list(risk.checks),
        "strategy_action": bundle.strategy_outcome.get("action"),
        "decision_eligibility_asserted": False,
    }
    return outcome


def native_portfolio_risk_decision_fingerprint(
    *,
    inputs: dict[str, Any],
    outcome: dict[str, Any],
) -> str:
    """Return the deterministic portfolio-risk-stage decision fingerprint."""
    return _sha(
        _canonical(
            [
                "portfolio_risk",
                inputs,
                outcome,
            ]
        )
    )
