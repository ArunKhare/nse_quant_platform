"""Tests for audited decision-run coverage reconciliation."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.audited_decision_reconciliation import (
    reconcile_audited_decision_run,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    STAGES,
    STRATEGY,
    VERSION,
)


def _coverage(*, covered: list[str] | None = None) -> dict[str, object]:
    covered = covered or []
    return {
        "version": VERSION,
        "strategy": STRATEGY,
        "definition_sha256": DEFINITION_SHA256,
        "stages": STAGES,
        "covered": covered,
        "unlinked": [],
        "missing": [
            requirement_id
            for requirement_id, _source, _need in __import__(
                "nse_quant.data_platform.native_strategy_requirements",
                fromlist=["REQUIREMENTS"],
            ).REQUIREMENTS
            if requirement_id not in covered
        ],
        "evidence_refs": {
            requirement_id: (
                f"silver://{requirement_id}?revision_id={'a' * 64}&recording_fingerprint={'b' * 64}&row_count=1"
            )
            for requirement_id in covered
        },
        "revision_id": "a" * 64,
        "recording_fingerprint": "b" * 64,
        "complete": False,
    }


def test_reconciles_strategy_only_run() -> None:
    result = reconcile_audited_decision_run(
        coverage_report=_coverage(covered=["market_session"]),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions={"strategy": "c" * 64},
        stage_recording_fingerprints={"strategy": "d" * 64},
    )
    assert result["run_id"] == "run-1"
    assert result["coverage"]["covered"] == ["market_session"]
    assert result["stages"][0]["replayed"] is True
    assert result["stages"][1] == {
        "stage": "portfolio_risk",
        "replayed": False,
        "reason": "STAGE_NOT_EXECUTED",
        "decision_eligibility_asserted": False,
    }
    assert result["complete"] is False
    assert result["decision_eligibility_asserted"] is False


def test_identity_requirement_remains_uncovered() -> None:
    result = reconcile_audited_decision_run(
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy",),
        stage_revisions={},
        stage_recording_fingerprints={},
    )
    assert "authoritative_identity_and_time" in result["coverage"]["missing"]
    assert result["complete"] is False
    assert result["decision_eligibility_asserted"] is False


def test_unknown_stage_rejected() -> None:
    with pytest.raises(Rejected, match="UNSUPPORTED_STAGE"):
        reconcile_audited_decision_run(
            coverage_report=_coverage(),
            run_id="run-1",
            stages=("execution",),
            stage_revisions={},
            stage_recording_fingerprints={},
        )


def test_duplicate_stage_rejected() -> None:
    with pytest.raises(Rejected, match="DUPLICATE_REQUESTED_DECISION_STAGE"):
        reconcile_audited_decision_run(
            coverage_report=_coverage(),
            run_id="run-1",
            stages=("strategy", "strategy"),
            stage_revisions={},
            stage_recording_fingerprints={},
        )


def test_invalid_coverage_identity_rejected() -> None:
    report = _coverage()
    report["revision_id"] = "not-a-pin"
    with pytest.raises(Rejected, match="EXACT_COVERAGE_REVISION_PIN_REQUIRED"):
        reconcile_audited_decision_run(
            coverage_report=report,
            run_id="run-1",
            stages=("strategy",),
            stage_revisions={},
            stage_recording_fingerprints={},
        )
