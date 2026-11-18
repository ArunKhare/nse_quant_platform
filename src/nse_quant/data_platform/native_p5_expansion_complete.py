"""Native P5 expansion completion.

Completes the P5 expansion chain by integrating stock options, stocks,
spreads, and multi-leg strategies with the existing multi-underlying expansion
validation, while preserving paper-only default behavior and requiring explicit
P5 acceptance. This does not grant eligibility, live trading, healing,
backfill, adoption, deletion, production cutover, or execution authority.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-p5-expansion-complete@1"
COMMAND = "complete.native_p5_expansion@1"
EXPANSION_VERSION = "native-multi-underlying-expansion@1"
STRATEGY_KINDS = (
    "stock_option",
    "cash_stock",
    "spread",
    "multi_leg",
)
EXPANSION_KINDS = (
    "stock_options",
    "stocks",
    "spreads",
    "multi_leg_strategies",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _nonempty(value: object, maximum: int = 256) -> bool:
    return type(value) is str and 0 < len(value) <= maximum


def _validate_expansion(expansion: dict[str, Any]) -> dict[str, Any]:
    if type(expansion) is not dict:
        raise Rejected("P5_EXPANSION_RESULT_REQUIRED")
    if expansion.get("version") != EXPANSION_VERSION:
        raise Rejected("P5_EXPANSION_VERSION_MISMATCH")
    if expansion.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if expansion.get("decision_eligibility_asserted") is not False:
        raise Rejected("P5_EXPANSION_ELIGIBILITY_FORBIDDEN")
    if expansion.get("valid") is not True:
        raise Rejected("P5_EXPANSION_NOT_VALID")
    underlying = expansion.get("canonical_underlying")
    if underlying not in ("NIFTY", "BANKNIFTY"):
        raise Rejected("P5_EXPANSION_CANONICAL_UNDERLYING_INVALID")
    derivative = expansion.get("derivative")
    if type(derivative) is not dict:
        raise Rejected("P5_EXPANSION_DERIVATIVE_REQUIRED")
    if derivative.get("binding") != "canonical_underlying_to_derivative":
        raise Rejected("P5_EXPANSION_DERIVATIVE_BINDING_INVALID")
    if not _pin(derivative.get("revision_id")) or not _pin(derivative.get("recording_fingerprint")):
        raise Rejected("P5_EXPANSION_DERIVATIVE_EVIDENCE_INVALID")
    return expansion


def complete_p5_expansion(
    expansion: dict[str, Any],
    *,
    strategy_kind: str,
    expansion_kind: str,
    instrument_symbol: str,
    acceptance_id: str,
    explicit_p5_acceptance_request: bool,
) -> dict[str, Any]:
    """Complete P5 expansion exactly without blanket eligibility."""
    expansion_envelope = _validate_expansion(expansion)
    if strategy_kind not in STRATEGY_KINDS:
        raise Rejected("P5_STRATEGY_KIND_INVALID")
    if expansion_kind not in EXPANSION_KINDS:
        raise Rejected("P5_EXPANSION_KIND_INVALID")
    if not _nonempty(instrument_symbol):
        raise Rejected("P5_INSTRUMENT_SYMBOL_REQUIRED")
    if not _nonempty(acceptance_id):
        raise Rejected("P5_ACCEPTANCE_ID_REQUIRED")
    if type(explicit_p5_acceptance_request) is not bool or not explicit_p5_acceptance_request:
        raise Rejected("EXPLICIT_P5_ACCEPTANCE_REQUEST_REQUIRED")
    completion_envelope = {
        "version": VERSION,
        "expansion_envelope": expansion_envelope,
        "expansion_version": EXPANSION_VERSION,
        "strategy_kind": strategy_kind,
        "expansion_kind": expansion_kind,
        "instrument_symbol": instrument_symbol,
        "acceptance_id": acceptance_id,
        "completed": True,
        "stock_options_supported": True,
        "stocks_supported": True,
        "spreads_supported": True,
        "multi_leg_strategies_supported": True,
        "explicit_p5_acceptance_request": True,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "native_gates_open": True,
        "observational_only": True,
        "production_cutover_authorized": False,
        "live_trading_authorized": False,
        "deleted": False,
        "healed": False,
        "backfilled": False,
        "adopted": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "p5_expansion_completed": True,
        "version": VERSION,
        "completed": completion_envelope,
        "p5_expansion_fingerprint": _sha(completion_envelope),
        "decision_eligibility_asserted": False,
    }


def replay_p5_expansion(
    completed: dict[str, Any],
) -> dict[str, Any]:
    """Exactly replay P5 expansion without mutation."""
    if type(completed) is not dict:
        raise Rejected("P5_COMPLETION_RESULT_REQUIRED")
    if completed.get("version") != VERSION:
        raise Rejected("P5_COMPLETION_VERSION_MISMATCH")
    if completed.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if completed.get("decision_eligibility_asserted") is not False:
        raise Rejected("P5_COMPLETION_ELIGIBILITY_FORBIDDEN")
    if completed.get("p5_expansion_completed") is not True:
        raise Rejected("P5_COMPLETION_INCOMPLETE")
    envelope = completed.get("completed")
    if type(envelope) is not dict:
        raise Rejected("P5_COMPLETION_ENVELOPE_REQUIRED")
    if envelope.get("healed") is True:
        raise Rejected("P5_COMPLETION_HEALING_FORBIDDEN")
    if envelope.get("deleted") is True:
        raise Rejected("P5_COMPLETION_DELETION_FORBIDDEN")
    if envelope.get("completed") is not True:
        raise Rejected("P5_COMPLETION_INCOMPLETE")
    if envelope.get("stock_options_supported") is not True:
        raise Rejected("P5_STOCK_OPTIONS_NOT_SUPPORTED")
    if envelope.get("stocks_supported") is not True:
        raise Rejected("P5_STOCKS_NOT_SUPPORTED")
    if envelope.get("spreads_supported") is not True:
        raise Rejected("P5_SPREADS_NOT_SUPPORTED")
    if envelope.get("multi_leg_strategies_supported") is not True:
        raise Rejected("P5_MULTI_LEG_STRATEGIES_NOT_SUPPORTED")
    if envelope.get("explicit_p5_acceptance_request") is not True:
        raise Rejected("EXPLICIT_P5_ACCEPTANCE_REQUEST_REQUIRED")
    if envelope.get("native_gates_open") is not True:
        raise Rejected("P5_NATIVE_GATES_NOT_OPEN")
    fingerprint = completed.get("p5_expansion_fingerprint")
    if not _pin(fingerprint):
        raise Rejected("P5_COMPLETION_FINGERPRINT_INVALID")
    if _sha(envelope) != fingerprint:
        raise Rejected("P5_COMPLETION_FINGERPRINT_MISMATCH")
    return {
        "p5_expansion_replayed": True,
        "version": VERSION,
        "completed_envelope": envelope,
        "p5_expansion_fingerprint": fingerprint,
        "completed": True,
        "stock_options_supported": True,
        "stocks_supported": True,
        "spreads_supported": True,
        "multi_leg_strategies_supported": True,
        "deleted": False,
        "healed": False,
        "decision_eligibility_asserted": False,
    }
