"""Tests for evidence-linked audited native decision-run binding."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.audited_decision_run import bind_decision_run_to_coverage, ensure_no_point_in_time_decision
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    STAGES,
    STRATEGY,
    VERSION,
)


def _report(*, covered: list[str] | None = None) -> dict[str, object]:
    covered = covered or []
    return {
        "version": VERSION,
        "strategy": STRATEGY,
        "definition_sha256": DEFINITION_SHA256,
        "stages": STAGES,
        "covered": covered,
        "missing": [
            requirement_id
            for requirement_id, _source, _need in __import__(
                "nse_quant.data_platform.native_strategy_requirements", fromlist=["REQUIREMENTS"]
            ).REQUIREMENTS
            if requirement_id not in covered
        ],
        "evidence_refs": {
            requirement_id: f"silver://{requirement_id}?revision_id={'a' * 64} \
            &recording_fingerprint={'b' * 64}&row_count=1"
            for requirement_id in covered
        },
        "revision_id": "a" * 64,
        "recording_fingerprint": "b" * 64,
    }


def test_binds_covered_requirement() -> None:
    refs = bind_decision_run_to_coverage(
        coverage_report=_report(covered=["market_session"]),
        stage="strategy",
        required_requirement_ids=frozenset({"market_session"}),
    )
    assert refs["market_session"].startswith("silver://market_session?")


def test_missing_required_coverage_rejected() -> None:
    with pytest.raises(Rejected, match="REQUIRED_COVERAGE_MISSING"):
        bind_decision_run_to_coverage(
            coverage_report=_report(),
            stage="strategy",
            required_requirement_ids=frozenset({"market_session"}),
        )


def test_identity_requirement_rejected() -> None:
    with pytest.raises(Rejected, match="AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE"):
        bind_decision_run_to_coverage(
            coverage_report=_report(covered=["authoritative_identity_and_time"]),
            stage="strategy",
            required_requirement_ids=frozenset({"authoritative_identity_and_time"}),
        )


def test_unknown_stage_rejected() -> None:
    with pytest.raises(Rejected, match="UNSUPPORTED_STAGE"):
        bind_decision_run_to_coverage(
            coverage_report=_report(covered=["market_session"]),
            stage="execution",
            required_requirement_ids=frozenset({"market_session"}),
        )


def test_point_in_time_decision_rejected() -> None:
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION_REJECTED"):
        ensure_no_point_in_time_decision({"decision_type": "POINT_IN_TIME_DECISION"})
