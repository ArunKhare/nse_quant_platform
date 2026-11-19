"""Report codec tests only; not native acquisition or decision integration."""

import json

import pytest
from native_failure_acceptance_report import FailureAcceptanceEvidence


def test_report_requires_successful_setup_call_and_teardown():
    evidence = FailureAcceptanceEvidence()
    evidence.register("test_not_run")
    for phase in ("setup", "call"):
        evidence.observe("test_partial", phase, "passed")
    for phase in ("setup", "call", "teardown"):
        evidence.observe("test_good", phase, "passed")
    evidence.observe("test_bad", "setup", "failed")
    evidence.observe("test_skipped", "setup", "skipped")
    report = json.loads(evidence.encode(1))
    statuses = {item["check_id"]: item["status"] for item in report["checks"]}
    assert statuses == {
        "test_not_run": "NOT_RUN",
        "test_partial": "NOT_RUN",
        "test_good": "PASSED",
        "test_bad": "FAILED",
        "test_skipped": "NOT_RUN",
    }
    assert not report["suite_passed"]
    assert not report["whole_platform_accepted"]
    assert not report["production_eligibility_asserted"]


def test_green_suite_never_promotes_blocked_real_world_requirements():
    evidence = FailureAcceptanceEvidence()
    for phase in ("setup", "call", "teardown"):
        evidence.observe("test_good", phase, "passed")
    report = json.loads(evidence.encode(0))
    assert report["suite_passed"]
    assert len(report["blocked_requirements"]) == 6
    assert report["independent_authority_supplied"] is False
    assert report["complete_original_decision_replay_verified"] is False
    assert report["mid_observation_concurrency_drift_exercised"] is False
    assert report["whole_platform_accepted"] is False
    evidence.collection_failed = True
    assert not json.loads(evidence.encode(0))["suite_passed"]


def test_report_rejects_raw_diagnostic_fields_duplicates_and_unbounded_cases():
    evidence = FailureAcceptanceEvidence()
    with pytest.raises(ValueError, match="CASE_ID"):
        evidence.register("C:/private/SECRET")
    evidence.observe("test_good", "setup", "passed")
    with pytest.raises(ValueError, match="DUPLICATE"):
        evidence.observe("test_good", "setup", "passed")
    with pytest.raises(ValueError, match="PHASE_OR_OUTCOME"):
        evidence.observe("test_other", "call", "SECRET_EXCEPTION")
    for index in range(126):
        evidence.register("test_bound_" + str(index))
    with pytest.raises(ValueError, match="CHECK_BOUND"):
        evidence.register("test_overflow")
    assert b"SECRET" not in evidence.encode(1)


def test_predeclared_integration_inventory_cannot_pass_with_deselected_cases():
    evidence = FailureAcceptanceEvidence(("test_first", "test_second"))
    for phase in ("setup", "call", "teardown"):
        evidence.observe("test_first", phase, "passed")
    report = json.loads(evidence.encode(0))
    assert report["suite_passed"] is False
    assert report["checks"] == [
        dict(
            check_id="test_first",
            status="PASSED",
            evidence_kind="ACTUAL_NATIVE_PRODUCER_INTEGRATION",
        ),
        dict(
            check_id="test_second",
            status="NOT_RUN",
            evidence_kind="ACTUAL_NATIVE_PRODUCER_INTEGRATION",
        ),
    ]
