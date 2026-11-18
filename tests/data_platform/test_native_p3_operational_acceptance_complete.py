import hashlib
import json

import pytest

from nse_quant.data_platform.native_p3_operational_acceptance_complete import (
    VERSION,
    complete_p3_operational_acceptance,
    replay_p3_operational_acceptance,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _day(label):
    return {
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "package_qa_passed": True,
        "integration_tests_passed": True,
        "operational_checks_passed": True,
        "evidence_chain_complete": True,
        "gold_admission_complete": True,
        "lifecycle_recovery_complete": True,
        "replayed": True,
    }


def _kwargs(**overrides):
    values = {
        "acceptance_id": "p3-acceptance-001",
        "explicit_p3_acceptance_request": True,
    }
    values.update(overrides)
    return values


def test_completes_p3_operational_acceptance():
    result = complete_p3_operational_acceptance(_day("day_1"), _day("day_2"), _day("day_3"), **_kwargs())
    assert result["p3_operational_acceptance_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["accepted"]
    assert envelope["accepted"] is True
    assert envelope["multi_day_integrated"] is True
    assert envelope["package_qa_passed"] is True
    assert envelope["integration_tests_passed"] is True
    assert envelope["operational_checks_passed"] is True
    assert envelope["evidence_chain_complete"] is True
    assert envelope["gold_admission_complete"] is True
    assert envelope["lifecycle_recovery_complete"] is True
    assert envelope["replayed"] is True
    assert envelope["explicit_p3_acceptance_request"] is True
    assert envelope["native_gates_open"] is True
    assert envelope["production_cutover_authorized"] is False
    assert envelope["live_trading_authorized"] is False
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["p3_operational_acceptance_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p3_operational_acceptance(result)
    assert replayed["p3_operational_acceptance_replayed"] is True
    assert replayed["accepted"] is True
    assert replayed["multi_day_integrated"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"acceptance_id": ""}, "P3_ACCEPTANCE_ID_REQUIRED"),
        ({"explicit_p3_acceptance_request": False}, "EXPLICIT_P3_ACCEPTANCE_REQUEST_REQUIRED"),
    ],
)
def test_rejects_invalid_acceptance_inputs(overrides, error):
    with pytest.raises(Rejected) as exc:
        complete_p3_operational_acceptance(_day("day_1"), _day("day_2"), _day("day_3"), **_kwargs(**overrides))
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (lambda value: value.update({"decision_eligibility_asserted": True}), "P3_DAY_1_ELIGIBILITY_FORBIDDEN"),
        (lambda value: value.update({"package_qa_passed": False}), "P3_DAY_1_PACKAGE_QA_NOT_PASSED"),
        (lambda value: value.update({"integration_tests_passed": False}), "P3_DAY_1_INTEGRATION_TESTS_NOT_PASSED"),
        (lambda value: value.update({"operational_checks_passed": False}), "P3_DAY_1_OPERATIONAL_CHECKS_NOT_PASSED"),
        (lambda value: value.update({"evidence_chain_complete": False}), "P3_DAY_1_EVIDENCE_CHAIN_INCOMPLETE"),
        (lambda value: value.update({"gold_admission_complete": False}), "P3_DAY_1_GOLD_ADMISSION_INCOMPLETE"),
        (lambda value: value.update({"lifecycle_recovery_complete": False}), "P3_DAY_1_LIFECYCLE_RECOVERY_INCOMPLETE"),
        (lambda value: value.update({"replayed": False}), "P3_DAY_1_REPLAY_INCOMPLETE"),
    ],
)
def test_rejects_forbidden_day_inputs(mutation, error):
    value = _day("day_1")
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p3_operational_acceptance(value, _day("day_2"), _day("day_3"), **_kwargs())
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
            "P3_ACCEPTANCE_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"p3_operational_acceptance_completed": False}),
            "P3_ACCEPTANCE_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p3_operational_acceptance_fingerprint": "short"}),
            "P3_ACCEPTANCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p3_operational_acceptance_fingerprint": "0" * 64}),
            "P3_ACCEPTANCE_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["accepted"].update({"healed": True}),
            "P3_ACCEPTANCE_HEALING_FORBIDDEN",
        ),
        (
            lambda value: value["accepted"].update({"deleted": True}),
            "P3_ACCEPTANCE_DELETION_FORBIDDEN",
        ),
        (
            lambda value: value["accepted"].update({"multi_day_integrated": False}),
            "P3_ACCEPTANCE_INCOMPLETE",
        ),
        (
            lambda value: value["accepted"].update({"explicit_p3_acceptance_request": False}),
            "EXPLICIT_P3_ACCEPTANCE_REQUEST_REQUIRED",
        ),
        (
            lambda value: value["accepted"].update({"native_gates_open": False}),
            "P3_NATIVE_GATES_NOT_OPEN",
        ),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = complete_p3_operational_acceptance(_day("day_1"), _day("day_2"), _day("day_3"), **_kwargs())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p3_operational_acceptance(value)
    assert exc.value.args[0] == error
