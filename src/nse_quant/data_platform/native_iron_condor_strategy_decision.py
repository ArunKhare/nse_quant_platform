"""Native iron-condor strategy decision evaluation; observational only.

Evaluates a strategy-stage decision solely from an evidence-linked native input
bundle. It never grants eligibility, enables live trading, heals a coverage gap,
or authorizes execution. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected


@dataclass(frozen=True)
class NativeStrategyDecisionInputBundle:
    coverage_revision_id: str
    coverage_recording_fingerprint: str
    evidence_refs: dict[str, str]
    market_session: dict[str, Any]
    iv_rank_and_history: dict[str, Any]
    iv_rv_spread: dict[str, Any]
    expected_move: dict[str, Any]
    effective_proposal_configuration: dict[str, Any]
    chain_time_expiry_spot: dict[str, Any]
    option_chain_and_contract_terms: dict[str, Any]
    candidate_liquidity: dict[str, Any]


_REQUIRED_REQUIREMENTS = frozenset(
    {
        "market_session",
        "iv_rank_and_history",
        "iv_rv_spread",
        "expected_move",
        "effective_proposal_configuration",
        "chain_time_expiry_spot",
        "option_chain_and_contract_terms",
        "candidate_liquidity",
    }
)


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


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise Rejected(f"{label}_MAPPING_REQUIRED")
    return value


def _require_positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Rejected(f"{label}_POSITIVE_NUMBER_REQUIRED")
    number = float(value)
    if number <= 0 or number != number or number in (float("inf"), float("-inf")):
        raise Rejected(f"{label}_POSITIVE_NUMBER_REQUIRED")
    return number


def validate_native_strategy_decision_input_bundle(
    bundle: NativeStrategyDecisionInputBundle,
) -> None:
    """Validate exact evidence-linked inputs for the strategy stage."""
    if type(bundle) is not NativeStrategyDecisionInputBundle:
        raise Rejected("TYPED_NATIVE_STRATEGY_INPUT_BUNDLE_REQUIRED")
    if not _pin(bundle.coverage_revision_id):
        raise Rejected("EXACT_COVERAGE_REVISION_PIN_REQUIRED")
    if not _pin(bundle.coverage_recording_fingerprint):
        raise Rejected("EXACT_COVERAGE_RECORDING_FINGERPRINT_REQUIRED")
    if type(bundle.evidence_refs) is not dict:
        raise Rejected("EXACT_EVIDENCE_REFS_REQUIRED")
    missing = sorted(_REQUIRED_REQUIREMENTS - set(bundle.evidence_refs))
    if missing:
        raise Rejected("REQUIRED_NATIVE_INPUT_COVERAGE_MISSING")
    if "authoritative_identity_and_time" in bundle.evidence_refs:
        raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")

    for label, value in (
        ("MARKET_SESSION", bundle.market_session),
        ("IV_RANK_AND_HISTORY", bundle.iv_rank_and_history),
        ("IV_RV_SPREAD", bundle.iv_rv_spread),
        ("EXPECTED_MOVE", bundle.expected_move),
        ("EFFECTIVE_PROPOSAL_CONFIGURATION", bundle.effective_proposal_configuration),
        ("CHAIN_TIME_EXPIRY_SPOT", bundle.chain_time_expiry_spot),
        ("OPTION_CHAIN_AND_CONTRACT_TERMS", bundle.option_chain_and_contract_terms),
        ("CANDIDATE_LIQUIDITY", bundle.candidate_liquidity),
    ):
        _require_mapping(value, label)

    if bundle.market_session.get("is_market_open") is not True:
        raise Rejected("MARKET_SESSION_NOT_OPEN")

    _require_positive_number(
        bundle.expected_move.get("expected_move_points"),
        "EXPECTED_MOVE_POINTS",
    )
    _require_positive_number(
        bundle.chain_time_expiry_spot.get("spot"),
        "CHAIN_SPOT",
    )

    liquidity = bundle.candidate_liquidity
    if liquidity.get("tradable") is not True:
        raise Rejected("CANDIDATE_LIQUIDITY_NOT_TRADABLE")


def evaluate_native_strategy_decision(
    bundle: NativeStrategyDecisionInputBundle,
) -> dict[str, Any]:
    """Evaluate an observational native strategy-stage decision."""
    validate_native_strategy_decision_input_bundle(bundle)

    iv = bundle.iv_rank_and_history
    spread = bundle.iv_rv_spread
    expected_move = _require_positive_number(
        bundle.expected_move.get("expected_move_points"),
        "EXPECTED_MOVE_POINTS",
    )
    spot = _require_positive_number(
        bundle.chain_time_expiry_spot.get("spot"),
        "CHAIN_SPOT",
    )
    configuration = bundle.effective_proposal_configuration

    minimum_credit = configuration.get("minimum_credit")
    if isinstance(minimum_credit, bool) or not isinstance(minimum_credit, (int, float)):
        raise Rejected("MINIMUM_CREDIT_NUMBER_REQUIRED")
    minimum_credit = float(minimum_credit)

    iv_rank = iv.get("iv_rank")
    iv_rv_spread = spread.get("iv_rv_spread")
    if isinstance(iv_rank, bool) or not isinstance(iv_rank, (int, float)):
        raise Rejected("IV_RANK_NUMBER_REQUIRED")
    if isinstance(iv_rv_spread, bool) or not isinstance(iv_rv_spread, (int, float)):
        raise Rejected("IV_RV_SPREAD_NUMBER_REQUIRED")

    expected_move_percent = expected_move / spot
    action = "monitor"
    reasons: list[str] = []

    if float(iv_rank) < 25.0:
        action = "no_trade"
        reasons.append("IV_RANK_BELOW_MONITOR_THRESHOLD")
    if float(iv_rv_spread) <= 0.0:
        action = "no_trade"
        reasons.append("IV_RV_SPREAD_NOT_POSITIVE")
    if expected_move_percent > 0.05:
        action = "no_trade"
        reasons.append("EXPECTED_MOVE_PERCENT_ABOVE_BOUND")
    if minimum_credit <= 0.0:
        action = "no_trade"
        reasons.append("MINIMUM_CREDIT_NOT_POSITIVE")

    outcome = {
        "decision_type": "NATIVE_STRATEGY_DECISION",
        "action": action,
        "reasons": reasons,
        "diagnostics": {
            "iv_rank": float(iv_rank),
            "iv_rv_spread": float(iv_rv_spread),
            "expected_move_points": expected_move,
            "expected_move_percent": expected_move_percent,
            "minimum_credit": minimum_credit,
        },
        "decision_eligibility_asserted": False,
    }
    return outcome


def native_strategy_decision_fingerprint(
    *,
    inputs: dict[str, Any],
    outcome: dict[str, Any],
) -> str:
    """Return the deterministic strategy-stage decision fingerprint."""
    return _sha(
        _canonical(
            [
                "strategy",
                inputs,
                outcome,
            ]
        )
    )
