import hashlib
import json

import pytest

from nse_quant.data_platform.native_p2_lifecycle_recovery_complete import (
    VERSION,
    complete_p2_lifecycle_recovery,
    replay_p2_lifecycle_recovery,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _lifecycle():
    envelope = {
        "version": "native-authority-evidence-completeness-report-audit-trail-lifecycle@1",
        "audit_trail": {"healed": False},
        "complete": True,
        "missing_obligations": [],
        "audit_integrated": True,
        "orphan_check_integrated": True,
        "final_audit_integrated": True,
        "lifecycle_stages": [
            "retained",
            "archived",
            "closed",
            "final_audited",
            "reconciled",
            "accepted",
            "validated",
            "round_tripped",
            "imported",
            "exported",
            "queried",
            "persisted",
        ],
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    return {
        "lifecycle_completed": True,
        "version": "native-authority-evidence-completeness-report-audit-trail-lifecycle@1",
        "lifecycle": envelope,
        "lifecycle_fingerprint": hashlib.sha256(_canonical(envelope)).hexdigest(),
        "decision_eligibility_asserted": False,
    }


def _kwargs(**overrides):
    values = {
        "recovery_kind": "retry",
        "recovery_outcome": "observed",
        "obligation_state": "resolved",
        "recovery_id": "p2-recovery-001",
        "explicit_p2_acceptance_request": True,
    }
    values.update(overrides)
    return values


def test_completes_p2_lifecycle_recovery():
    lifecycle = _lifecycle()
    result = complete_p2_lifecycle_recovery(lifecycle, **_kwargs())
    assert result["p2_lifecycle_recovery_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["recovered"]
    assert envelope["recovered"] is True
    assert envelope["recovery_observed"] is True
    assert envelope["original_failure_preserved"] is True
    assert envelope["recovery_kind"] == "retry"
    assert envelope["recovery_outcome"] == "observed"
    assert envelope["obligation_state"] == "resolved"
    assert envelope["recovery_id"] == "p2-recovery-001"
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert envelope["explicit_p2_acceptance_request"] is True
    assert result["p2_lifecycle_recovery_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p2_lifecycle_recovery(result)
    assert replayed["p2_lifecycle_recovery_replayed"] is True
    assert replayed["recovered"] is True
    assert replayed["original_failure_preserved"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"recovery_kind": "unknown"}, "P2_RECOVERY_KIND_INVALID"),
        ({"recovery_outcome": "unknown"}, "P2_RECOVERY_OUTCOME_INVALID"),
        ({"obligation_state": "unknown"}, "P2_OBLIGATION_STATE_INVALID"),
        ({"recovery_id": ""}, "P2_RECOVERY_ID_REQUIRED"),
        ({"explicit_p2_acceptance_request": False}, "EXPLICIT_P2_ACCEPTANCE_REQUEST_REQUIRED"),
    ],
)
def test_rejects_invalid_recovery_inputs(overrides, error):
    with pytest.raises(Rejected) as exc:
        complete_p2_lifecycle_recovery(_lifecycle(), **_kwargs(**overrides))
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (lambda value: value.update({"decision_eligibility_asserted": True}), "P2_LIFECYCLE_ELIGIBILITY_FORBIDDEN"),
        (lambda value: value.update({"lifecycle_completed": False}), "P2_LIFECYCLE_INCOMPLETE"),
        (lambda value: value.update({"lifecycle_fingerprint": "short"}), "P2_LIFECYCLE_FINGERPRINT_INVALID"),
        (lambda value: value.update({"lifecycle_fingerprint": "0" * 64}), "P2_LIFECYCLE_FINGERPRINT_MISMATCH"),
        (lambda value: value["lifecycle"].update({"healed": True}), "P2_LIFECYCLE_HEALING_FORBIDDEN"),
        (lambda value: value["lifecycle"].update({"complete": False}), "P2_LIFECYCLE_INCOMPLETE"),
    ],
)
def test_rejects_forbidden_lifecycle_inputs(mutation, error):
    value = _lifecycle()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p2_lifecycle_recovery(value, **_kwargs())
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
            "P2_RECOVERY_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"p2_lifecycle_recovery_completed": False}),
            "P2_RECOVERY_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p2_lifecycle_recovery_fingerprint": "short"}),
            "P2_RECOVERY_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p2_lifecycle_recovery_fingerprint": "0" * 64}),
            "P2_RECOVERY_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["recovered"].update({"healed": True}),
            "P2_RECOVERY_HEALING_FORBIDDEN",
        ),
        (
            lambda value: value["recovered"].update({"deleted": True}),
            "P2_RECOVERY_DELETION_FORBIDDEN",
        ),
        (
            lambda value: value["recovered"].update({"original_failure_preserved": False}),
            "P2_ORIGINAL_FAILURE_NOT_PRESERVED",
        ),
        (
            lambda value: value["recovered"].update({"explicit_p2_acceptance_request": False}),
            "EXPLICIT_P2_ACCEPTANCE_REQUEST_REQUIRED",
        ),
        (
            lambda value: value["recovered"].update({"native_gates_open": False}),
            "P2_NATIVE_GATES_NOT_OPEN",
        ),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = complete_p2_lifecycle_recovery(_lifecycle(), **_kwargs())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p2_lifecycle_recovery(value)
    assert exc.value.args[0] == error
