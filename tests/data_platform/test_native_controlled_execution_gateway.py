"""Tests for the controlled execution gateway."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_controlled_execution_gateway import (
    evaluate_execution_authorization,
    place_order,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _admitted() -> dict[str, object]:
    return {
        "admission_determined": True,
        "admitted": True,
        "decision_eligibility_asserted": False,
        "execution_authorized": False,
        "gold_revision_id": "a" * 64,
        "gold_recording_fingerprint": "b" * 64,
        "point_in_time_decision": False,
    }


def _config(mode: str) -> dict[str, object]:
    return {
        "mode": mode,
        "live_enabled": True,
        "explicit_user_authorization": True,
        "kill_switch_engaged": False,
    }


def test_paper_mode_not_authorized() -> None:
    result = evaluate_execution_authorization(
        execution_config=_config("paper"),
        admitted_decision=_admitted(),
    )
    assert result["execution_authorized"] is False
    assert result["paper_only"] is True
    assert result["reason"] == "PAPER_OR_DRY_RUN_ONLY"


def test_live_mode_authorized() -> None:
    result = evaluate_execution_authorization(
        execution_config=_config("live"),
        admitted_decision=_admitted(),
    )
    assert result["execution_authorized"] is True
    assert result["paper_only"] is False
    assert result["reason"] == "LIVE_EXECUTION_AUTHORIZED"


def test_live_disabled_rejected() -> None:
    config = _config("live")
    config["live_enabled"] = False
    with pytest.raises(Rejected, match="LIVE_EXECUTION_DISABLED"):
        evaluate_execution_authorization(
            execution_config=config,
            admitted_decision=_admitted(),
        )


def test_kill_switch_rejected() -> None:
    config = _config("live")
    config["kill_switch_engaged"] = True
    with pytest.raises(Rejected, match="KILL_SWITCH_ENGAGED"):
        evaluate_execution_authorization(
            execution_config=config,
            admitted_decision=_admitted(),
        )


def test_point_in_time_decision_rejected() -> None:
    admitted = _admitted()
    admitted["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        evaluate_execution_authorization(
            execution_config=_config("live"),
            admitted_decision=admitted,
        )


def test_paper_order_not_placed() -> None:
    result = place_order(
        execution_config=_config("paper"),
        admitted_decision=_admitted(),
        order_request={
            "underlying": "NIFTY",
            "expiry": "2026-11-26",
            "legs": [],
        },
    )
    assert result["placed"] is False
    assert result["order_id"] is None
    assert result["decision_eligibility_asserted"] is False
