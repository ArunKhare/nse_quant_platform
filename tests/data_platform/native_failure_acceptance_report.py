"""Sanitized pytest evidence for this bounded suite; never platform admission evidence."""

from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from typing import Any

import pytest

VERSION = "native-failure-acceptance-evidence@1"
MAX_CHECKS = 128
MAX_BYTES = 65536
BLOCKED = (
    "INDEPENDENT_GOVERNANCE_AND_KEY_LIFECYCLE",
    "AUTHORITATIVE_IDENTITY_AND_AUTHORIZED_REVOCATION",
    "INDEPENDENT_AVAILABILITY_AND_ECONOMIC_VALIDITY",
    "NEW_ELIGIBLE_PUBLICATION_CONTRACT",
    "COMPLETE_NATIVE_STRATEGY_DECISION_REPLAY",
    "WHOLE_NATIVE_OPERATIONAL_ACCEPTANCE",
)


EXPECTED_CASES = (
    "test_actual_capture_revalidation_refuses_and_does_not_write",
    "test_actual_frontier_row_bound_is_not_hidden_by_success_filter",
    "test_actual_frontier_text_bound_no_limit_monkeypatch_or_salvage",
    "test_ambiguous_assessment_graph_blocks_before_good_payload_selection",
    "test_current_publication_drift_changes_complete_input_even_when_both_outcomes_reject",
    "test_frontier_rejects_unknown_objects_and_operational_failure_is_not_refusal",
    "test_missing_capture_final_audit_is_not_healed_by_successful_retry",
    "test_missing_publication_final_audit_is_not_a_policy_only_match",
    "test_real_bronze_conflict_invalidates_gold_stage_not_archived_policy_replay",
    "test_real_capture_final_audit_exception_preserves_domain_and_failed_origin",
    "test_request_axes_are_not_refreshed_to_make_a_capture_match",
    "test_retained_database_tampering_never_uses_an_old_good_reader_cache[bytes]",
    "test_retained_database_tampering_never_uses_an_old_good_reader_cache[eligibility]",
    "test_retained_database_tampering_never_uses_an_old_good_reader_cache[links]",
    "test_retained_database_tampering_never_uses_an_old_good_reader_cache[status]",
    "test_scoped_unlinked_obligation_survives_successful_retry[failed]",
    "test_scoped_unlinked_obligation_survives_successful_retry[interrupted]",
    "test_scoped_unlinked_obligation_survives_successful_retry[running]",
    "test_stage_artifact_damage_does_not_repair_or_destroy_retained_refusal[changed]",
    "test_stage_artifact_damage_does_not_repair_or_destroy_retained_refusal[missing]",
)


class FailureAcceptanceEvidence:
    def __init__(self, expected_cases: tuple[str, ...] = ()) -> None:
        self.checks: dict[str, dict[str, str]] = {}
        self.collection_failed = False
        for case in expected_cases:
            self.register(case)

    def register(self, case: str) -> None:
        if re.fullmatch(r"test_[a-z0-9_]+(?:\[[a-z0-9_-]+\])?", case) is None:
            raise ValueError("UNSUPPORTED_SANITIZED_ACCEPTANCE_CASE_ID")
        if case not in self.checks and len(self.checks) >= MAX_CHECKS:
            raise ValueError("ACCEPTANCE_CHECK_BOUND")
        self.checks.setdefault(case, {})

    def observe(self, case: str, phase: str, outcome: str) -> None:
        self.register(case)
        if phase not in {"setup", "call", "teardown"} or outcome not in {
            "passed",
            "failed",
            "skipped",
        }:
            raise ValueError("UNSUPPORTED_ACCEPTANCE_PHASE_OR_OUTCOME")
        if phase in self.checks[case]:
            raise ValueError("DUPLICATE_ACCEPTANCE_PHASE")
        self.checks[case][phase] = outcome

    def encode(self, exitstatus: int) -> bytes:
        checks: list[dict[str, str]] = []
        for case, phases in sorted(self.checks.items()):
            status = "NOT_RUN"
            if "failed" in phases.values():
                status = "FAILED"
            elif phases == dict.fromkeys(("setup", "call", "teardown"), "passed"):
                status = "PASSED"
            checks.append(
                dict(
                    check_id=case, status=status, evidence_kind="ACTUAL_NATIVE_PRODUCER_INTEGRATION"
                )
            )
        complete = bool(checks) and all(item["status"] == "PASSED" for item in checks)
        value = dict(
            version=VERSION,
            python_version=platform.python_version(),
            pytest_exitstatus=exitstatus,
            collection_failed=self.collection_failed,
            suite_passed=complete and exitstatus == 0 and not self.collection_failed,
            checks=checks,
            blocked_requirements=list(BLOCKED),
            production_eligibility_asserted=False,
            whole_platform_accepted=False,
            independent_authority_supplied=False,
            complete_original_decision_replay_verified=False,
            mid_observation_concurrency_drift_exercised=False,
            real_operational_environment_verified=False,
        )
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError("ACCEPTANCE_REPORT_BYTE_BOUND")
        return raw


_evidence = FailureAcceptanceEvidence(EXPECTED_CASES)


def _case(nodeid: str) -> str | None:
    path, separator, case = nodeid.partition("::")
    if not separator or Path(path).name != "test_native_failure_acceptance.py":
        return None
    return case


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        case = _case(item.nodeid)
        if case is not None:
            _evidence.register(case)


def pytest_collectreport(report: Any) -> None:
    if report.failed:
        _evidence.collection_failed = True


def pytest_runtest_logreport(report: Any) -> None:
    case = _case(report.nodeid)
    if case is not None:
        _evidence.observe(case, report.when, report.outcome)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    destination = os.environ.get("NSE_NATIVE_FAILURE_REPORT")
    if destination:
        path = Path(destination)
        raw = _evidence.encode(int(exitstatus))
        with path.open("xb") as handle:
            handle.write(raw)


@pytest.hookimpl
def pytest_report_header() -> str:
    return "Native failure acceptance: synthetic research evidence; production holds remain"
