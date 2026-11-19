import hashlib
import json

import pytest

from nse_quant.data_platform.native_p1_gold_admission_chain_complete import (
    VERSION,
    complete_p1_gold_admission_chain,
    replay_p1_gold_admission_chain,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _gold():
    return {
        "version": "native-iron-condor-decision-gold@1",
        "strategy": STRATEGY,
        "run_id": "p1-admission-run-001",
        "reconciliation_revision_id": "a" * 64,
        "reconciliation_recording_fingerprint": "b" * 64,
        "identity_time_evidence_revision_id": "c" * 64,
        "identity_time_evidence_recording_fingerprint": "d" * 64,
        "availability_economic_evidence_revision_id": "e" * 64,
        "availability_economic_evidence_recording_fingerprint": "f" * 64,
        "stages": [
            {"stage": "strategy", "replayed": True, "decision_eligibility_asserted": False},
            {"stage": "portfolio_risk", "replayed": True, "decision_eligibility_asserted": False},
        ],
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def _reconciliation():
    return {
        "complete": True,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def _kwargs(**overrides):
    values = {
        "admission_kind": "admission",
        "authority_authenticated": True,
        "identity_valid": True,
        "temporal_matched": True,
        "lifecycle_resolved": True,
        "execution_mode": "paper",
        "explicit_p1_acceptance_request": True,
    }
    values.update(overrides)
    return values


def test_completes_p1_gold_admission_chain():
    result = complete_p1_gold_admission_chain(_gold(), _reconciliation(), **_kwargs())
    assert result["p1_gold_admission_chain_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["admitted"]
    assert envelope["admission_determined"] is True
    assert envelope["admitted"] is True
    assert envelope["reason"] == "SUFFICIENT_ELIGIBLE_ADMISSION_CONTRACT_SATISFIED"
    assert envelope["point_in_time_decision"] is False
    assert envelope["decision_eligibility_asserted"] is False
    assert envelope["execution_authorized"] is False
    assert envelope["production_cutover_authorized"] is False
    assert envelope["live_trading_authorized"] is False
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert envelope["explicit_p1_acceptance_request"] is True
    assert result["p1_gold_admission_chain_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p1_gold_admission_chain(result)
    assert replayed["p1_gold_admission_chain_replayed"] is True
    assert replayed["admitted"] is True
    assert replayed["point_in_time_decision"] is False
    assert replayed["decision_eligibility_asserted"] is False
    assert replayed["deleted"] is False
    assert replayed["healed"] is False


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"admission_kind": "unknown"}, "P1_ADMISSION_KIND_INVALID"),
        ({"authority_authenticated": False}, "AUTHORITY_NOT_AUTHENTICATED"),
        ({"identity_valid": False}, "IDENTITY_NOT_VALID"),
        ({"temporal_matched": False}, "TEMPORAL_NOT_MATCHED"),
        ({"lifecycle_resolved": False}, "LIFECYCLE_NOT_RESOLVED"),
        ({"execution_mode": "unknown"}, "P1_EXECUTION_MODE_INVALID"),
        ({"explicit_p1_acceptance_request": False}, "EXPLICIT_P1_ACCEPTANCE_REQUEST_REQUIRED"),
    ],
)
def test_rejects_invalid_admission_inputs(overrides, error):
    with pytest.raises(Rejected) as exc:
        complete_p1_gold_admission_chain(_gold(), _reconciliation(), **_kwargs(**overrides))
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
            "DECISION_GOLD_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"version": "wrong"}),
            "DECISION_GOLD_VERSION_MISMATCH",
        ),
        (
            lambda value: value.update({"strategy": "wrong"}),
            "DECISION_GOLD_STRATEGY_MISMATCH",
        ),
        (lambda value: value.update({"run_id": ""}), "DECISION_GOLD_RUN_ID_REQUIRED"),
        (
            lambda value: value.update({"reconciliation_revision_id": "short"}),
            "DECISION_GOLD_RECONCILIATION_EVIDENCE_INVALID",
        ),
        (
            lambda value: value.update({"identity_time_evidence_revision_id": "short"}),
            "DECISION_GOLD_IDENTITY_TIME_EVIDENCE_INVALID",
        ),
        (
            lambda value: value.update({"availability_economic_evidence_revision_id": "short"}),
            "DECISION_GOLD_AVAILABILITY_ECONOMIC_EVIDENCE_INVALID",
        ),
        (lambda value: value.update({"stages": []}), "DECISION_GOLD_STAGES_REQUIRED"),
        (
            lambda value: value["stages"][0].update({"replayed": False}),
            "DECISION_GOLD_STAGE_REPLAY_INCOMPLETE",
        ),
        (
            lambda value: value["stages"][1].update({"decision_eligibility_asserted": True}),
            "DECISION_GOLD_STAGE_ELIGIBILITY_FORBIDDEN",
        ),
    ],
)
def test_rejects_forbidden_gold_inputs(mutation, error):
    value = _gold()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p1_gold_admission_chain(value, _reconciliation(), **_kwargs())
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (lambda value: value.update({"decision_eligibility_asserted": True}), "RECONCILIATION_ELIGIBILITY_FORBIDDEN"),
        (lambda value: value.update({"complete": False}), "RECONCILIATION_EVIDENCE_INCOMPLETE"),
    ],
)
def test_rejects_forbidden_reconciliation_inputs(mutation, error):
    value = _reconciliation()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p1_gold_admission_chain(_gold(), value, **_kwargs())
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
            "P1_ADMISSION_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"p1_gold_admission_chain_completed": False}),
            "P1_ADMISSION_CHAIN_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p1_gold_admission_chain_fingerprint": "short"}),
            "P1_ADMISSION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p1_gold_admission_chain_fingerprint": "0" * 64}),
            "P1_ADMISSION_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["admitted"].update({"healed": True}),
            "P1_ADMISSION_HEALING_FORBIDDEN",
        ),
        (
            lambda value: value["admitted"].update({"deleted": True}),
            "P1_ADMISSION_DELETION_FORBIDDEN",
        ),
        (
            lambda value: value["admitted"].update({"backfilled": True}),
            "P1_ADMISSION_BACKFILL_FORBIDDEN",
        ),
        (
            lambda value: value["admitted"].update({"adopted": True}),
            "P1_ADMISSION_ADOPTION_FORBIDDEN",
        ),
        (
            lambda value: value["admitted"].update({"explicit_p1_acceptance_request": False}),
            "EXPLICIT_P1_ACCEPTANCE_REQUEST_REQUIRED",
        ),
        (
            lambda value: value["admitted"].update({"native_gates_open": False}),
            "P1_NATIVE_GATES_NOT_OPEN",
        ),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = complete_p1_gold_admission_chain(_gold(), _reconciliation(), **_kwargs())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p1_gold_admission_chain(value)
    assert exc.value.args[0] == error
