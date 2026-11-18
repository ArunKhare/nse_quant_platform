import hashlib
import json

import pytest

from nse_quant.data_platform.native_p4_controlled_execution_complete import (
    VERSION,
    complete_p4_controlled_execution,
    replay_p4_controlled_execution,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _gateway():
    return {
        "version": "native-controlled-execution-gateway@1",
        "execution_authorized": True,
        "mode": "live",
        "paper_only": False,
        "reason": "LIVE_EXECUTION_AUTHORIZED",
        "decision_eligibility_asserted": False,
        "point_in_time_decision": False,
    }


def _kwargs(**overrides):
    values = {
        "order_id": "p4-order-001",
        "order_status": "partially_filled",
        "filled_quantity": 50,
        "total_quantity": 100,
        "margin_required": 1000.0,
        "margin_available": 2000.0,
        "reconciliation_outcome": "matched",
        "exit_reason": "target",
        "explicit_p4_acceptance_request": True,
    }
    values.update(overrides)
    return values


def test_completes_p4_controlled_execution():
    gateway = _gateway()
    result = complete_p4_controlled_execution(gateway, **_kwargs())
    assert result["p4_controlled_execution_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["completed"]
    assert envelope["completed"] is True
    assert envelope["order_placed"] is True
    assert envelope["reconciled"] is True
    assert envelope["margin_checked"] is True
    assert envelope["partial_fill_supported"] is True
    assert envelope["rule_based_exit_supported"] is True
    assert envelope["order_id"] == "p4-order-001"
    assert envelope["order_status"] == "partially_filled"
    assert envelope["filled_quantity"] == 50
    assert envelope["total_quantity"] == 100
    assert envelope["margin_required"] == 1000.0
    assert envelope["margin_available"] == 2000.0
    assert envelope["reconciliation_outcome"] == "matched"
    assert envelope["exit_reason"] == "target"
    assert envelope["explicit_p4_acceptance_request"] is True
    assert envelope["native_gates_open"] is True
    assert envelope["production_cutover_authorized"] is False
    assert envelope["live_trading_authorized"] is False
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["p4_controlled_execution_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p4_controlled_execution(result)
    assert replayed["p4_controlled_execution_replayed"] is True
    assert replayed["completed"] is True
    assert replayed["order_placed"] is True
    assert replayed["reconciled"] is True
    assert replayed["margin_checked"] is True
    assert replayed["partial_fill_supported"] is True
    assert replayed["rule_based_exit_supported"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"order_id": ""}, "P4_ORDER_ID_REQUIRED"),
        ({"order_status": "unknown"}, "P4_ORDER_STATUS_INVALID"),
        ({"filled_quantity": -1}, "P4_FILLED_QUANTITY_INVALID"),
        ({"total_quantity": 0}, "P4_TOTAL_QUANTITY_INVALID"),
        ({"filled_quantity": 200}, "P4_FILLED_QUANTITY_EXCEEDS_TOTAL"),
        ({"margin_required": -1}, "P4_MARGIN_INVALID"),
        ({"margin_available": -1}, "P4_MARGIN_INVALID"),
        ({"margin_available": 500.0}, "P4_MARGIN_INSUFFICIENT"),
        ({"reconciliation_outcome": "unknown"}, "P4_RECONCILIATION_OUTCOME_INVALID"),
        ({"exit_reason": "unknown"}, "P4_EXIT_REASON_INVALID"),
        ({"explicit_p4_acceptance_request": False}, "EXPLICIT_P4_ACCEPTANCE_REQUEST_REQUIRED"),
    ],
)
def test_rejects_invalid_execution_inputs(overrides, error):
    with pytest.raises(Rejected) as exc:
        complete_p4_controlled_execution(_gateway(), **_kwargs(**overrides))
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (lambda value: value.update({"decision_eligibility_asserted": True}), "P4_GATEWAY_ELIGIBILITY_FORBIDDEN"),
        (lambda value: value.update({"version": "wrong"}), "P4_GATEWAY_VERSION_MISMATCH"),
        (lambda value: value.update({"execution_authorized": False}), "P4_GATEWAY_EXECUTION_NOT_AUTHORIZED"),
        (lambda value: value.update({"mode": "paper"}), "P4_GATEWAY_MODE_INVALID"),
        (lambda value: value.update({"paper_only": True}), "P4_GATEWAY_PAPER_ONLY_INVALID"),
    ],
)
def test_rejects_forbidden_gateway_inputs(mutation, error):
    value = _gateway()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p4_controlled_execution(value, **_kwargs())
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda value: value.update({"point_in_time_decision": True}),
            "POINT_IN_TIME_DECISION",
        ),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "P4_EXECUTION_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"p4_controlled_execution_completed": False}),
            "P4_EXECUTION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p4_controlled_execution_fingerprint": "short"}),
            "P4_EXECUTION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p4_controlled_execution_fingerprint": "0" * 64}),
            "P4_EXECUTION_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["completed"].update({"healed": True}),
            "P4_EXECUTION_HEALING_FORBIDDEN",
        ),
        (
            lambda value: value["completed"].update({"deleted": True}),
            "P4_EXECUTION_DELETION_FORBIDDEN",
        ),
        (
            lambda value: value["completed"].update({"reconciled": False}),
            "P4_RECONCILIATION_NOT_COMPLETED",
        ),
        (
            lambda value: value["completed"].update({"margin_checked": False}),
            "P4_MARGIN_NOT_CHECKED",
        ),
        (
            lambda value: value["completed"].update({"partial_fill_supported": False}),
            "P4_PARTIAL_FILL_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"rule_based_exit_supported": False}),
            "P4_RULE_BASED_EXIT_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"explicit_p4_acceptance_request": False}),
            "EXPLICIT_P4_ACCEPTANCE_REQUEST_REQUIRED",
        ),
        (
            lambda value: value["completed"].update({"native_gates_open": False}),
            "P4_NATIVE_GATES_NOT_OPEN",
        ),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = complete_p4_controlled_execution(_gateway(), **_kwargs())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p4_controlled_execution(value)
    assert exc.value.args[0] == error
