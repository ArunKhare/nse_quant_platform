"""Multi-underlying expansion validation for native decisions.

Validates canonical underlying support and derivative binding for NIFTY and
BANKNIFTY without granting eligibility, live trading, healing, backfill,
adoption, or execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-multi-underlying-expansion@1"
COMMAND = "validate.native_multi_underlying_expansion@1"
SUPPORTED_UNDERLYINGS = ("NIFTY", "BANKNIFTY")


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_multi_underlying_expansion(
    document: dict[str, Any],
) -> dict[str, Any]:
    """Validate canonical underlying support and derivative binding."""
    if type(document) is not dict:
        raise Rejected("MULTI_UNDERLYING_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("MULTI_UNDERLYING_VERSION_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("MULTI_UNDERLYING_ELIGIBILITY_FORBIDDEN")
    underlying = document.get("canonical_underlying")
    if underlying not in SUPPORTED_UNDERLYINGS:
        raise Rejected("MULTI_UNDERLYING_CANONICAL_UNDERLYING_INVALID")
    derivative = document.get("derivative")
    if type(derivative) is not dict:
        raise Rejected("MULTI_UNDERLYING_DERIVATIVE_REQUIRED")
    if derivative.get("binding") != "canonical_underlying_to_derivative":
        raise Rejected("MULTI_UNDERLYING_DERIVATIVE_BINDING_INVALID")
    if not _pin(derivative.get("revision_id")) or not _pin(derivative.get("recording_fingerprint")):
        raise Rejected("MULTI_UNDERLYING_DERIVATIVE_EVIDENCE_INVALID")
    return {
        "valid": True,
        "version": VERSION,
        "canonical_underlying": underlying,
        "supported_underlyings": list(SUPPORTED_UNDERLYINGS),
        "decision_eligibility_asserted": False,
    }
