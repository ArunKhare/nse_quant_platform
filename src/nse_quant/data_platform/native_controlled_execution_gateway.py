"""Controlled execution gateway for native iron-condor decisions.

Provides a narrowly scoped execution gateway that remains paper-only by default.
Live order placement requires an explicitly enabled configuration, an admitted
Gold decision candidate, and an explicit execution authorization flag. No
eligibility grant, healing, backfill, adoption, or automatic execution.
POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import Rejected

VERSION = "native-controlled-execution-gateway@1"
COMMAND = "execute.native_controlled_execution_gateway@1"


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def evaluate_execution_authorization(
    *,
    execution_config: dict[str, Any],
    admitted_decision: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate whether a decision may proceed to controlled execution."""
    if type(execution_config) is not dict:
        raise Rejected("EXECUTION_CONFIG_REQUIRED")
    if type(admitted_decision) is not dict:
        raise Rejected("ADMITTED_DECISION_REQUIRED")
    if admitted_decision.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if admitted_decision.get("decision_eligibility_asserted") is not False:
        raise Rejected("EXECUTION_ELIGIBILITY_FORBIDDEN")
    if admitted_decision.get("admission_determined") is not True:
        raise Rejected("EXECUTION_ADMISSION_REQUIRED")
    if admitted_decision.get("admitted") is not True:
        raise Rejected("EXECUTION_ADMISSION_NOT_GRANTED")
    if admitted_decision.get("execution_authorized") is not False:
        raise Rejected("EXECUTION_AUTHORIZATION_INVALID")

    mode = execution_config.get("mode")
    if mode not in ("paper", "dry_run", "live"):
        raise Rejected("EXECUTION_MODE_INVALID")
    if mode == "live":
        if execution_config.get("live_enabled") is not True:
            raise Rejected("LIVE_EXECUTION_DISABLED")
        if execution_config.get("explicit_user_authorization") is not True:
            raise Rejected("EXPLICIT_USER_AUTHORIZATION_REQUIRED")
        if execution_config.get("kill_switch_engaged") is True:
            raise Rejected("KILL_SWITCH_ENGAGED")
        if not _pin(admitted_decision.get("gold_revision_id")):
            raise Rejected("EXECUTION_GOLD_REVISION_INVALID")
        if not _pin(admitted_decision.get("gold_recording_fingerprint")):
            raise Rejected("EXECUTION_GOLD_FINGERPRINT_INVALID")

    return {
        "execution_authorized": mode == "live",
        "mode": mode,
        "paper_only": mode != "live",
        "reason": ("LIVE_EXECUTION_AUTHORIZED" if mode == "live" else "PAPER_OR_DRY_RUN_ONLY"),
        "decision_eligibility_asserted": False,
    }


def place_order(
    *,
    execution_config: dict[str, Any],
    admitted_decision: dict[str, Any],
    order_request: dict[str, Any],
) -> dict[str, Any]:
    """Place an order only through the controlled execution gateway."""
    authorization = evaluate_execution_authorization(
        execution_config=execution_config,
        admitted_decision=admitted_decision,
    )
    if type(order_request) is not dict:
        raise Rejected("ORDER_REQUEST_REQUIRED")
    if authorization["execution_authorized"] is not True:
        return {
            "placed": False,
            "mode": authorization["mode"],
            "reason": authorization["reason"],
            "order_id": None,
            "decision_eligibility_asserted": False,
        }
    required = ("underlying", "expiry", "legs")
    for field in required:
        if field not in order_request:
            raise Rejected(f"ORDER_{field.upper()}_REQUIRED")
    return {
        "placed": True,
        "mode": "live",
        "reason": "LIVE_EXECUTION_AUTHORIZED",
        "order_id": "controlled-execution-pending-broker-integration",
        "decision_eligibility_asserted": False,
    }
