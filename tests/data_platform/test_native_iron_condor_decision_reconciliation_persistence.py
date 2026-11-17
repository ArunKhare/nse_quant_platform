"""Tests for native iron-condor decision reconciliation persistence."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    initialize_audited_decision_reconciliation_silver,
)
from nse_quant.data_platform.native_iron_condor_decision_reconciliation_persistence import (
    build_native_iron_condor_decision_reconciliation,
    persist_native_iron_condor_decision_reconciliation,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    STAGES,
    STRATEGY,
    VERSION,
)


def _coverage() -> dict[str, object]:
    covered = ["market_session"]
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
            "market_session": (
                "silver://market_session?revision_id="
                + "a" * 64
                + "&recording_fingerprint="
                + "b" * 64
                + "&row_count=1"
            )
        },
        "revision_id": "a" * 64,
        "recording_fingerprint": "b" * 64,
        "complete": False,
    }


def _pins() -> tuple[dict[str, str], dict[str, str]]:
    revisions = {
        "strategy": "c" * 64,
        "portfolio_risk": "d" * 64,
    }
    fingerprints = {
        "strategy": "e" * 64,
        "portfolio_risk": "f" * 64,
    }
    return revisions, fingerprints


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "native-reconciliation-persistence.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_audited_decision_reconciliation_silver(connection)
        yield connection


def test_builds_reconciliation_with_silver_version() -> None:
    revisions, fingerprints = _pins()
    reconciliation = build_native_iron_condor_decision_reconciliation(
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
    )
    assert reconciliation["version"].startswith("native-audited-decision-reconciliation-silver-recording@")
    assert reconciliation["strategy"] == STRATEGY
    assert reconciliation["complete"] is False
    assert reconciliation["decision_eligibility_asserted"] is False


def test_persists_and_replays_reconciliation(target) -> None:
    from nse_quant.data_platform.audited_decision_reconciliation_silver import (
        reconciliation_context,
    )

    revisions, fingerprints = _pins()
    reconciliation = build_native_iron_condor_decision_reconciliation(
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
    )
    result = persist_native_iron_condor_decision_reconciliation(
        target,
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
        expected_context_sha256=reconciliation_context(reconciliation),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["recording"]["decision_eligibility_asserted"] is False
    assert result["replay"]["replayed"] is True
    assert result["replay"]["reconciliation"] == reconciliation
    assert result["decision_eligibility_asserted"] is False


def test_duplicate_reconciliation_rejected(target) -> None:
    from nse_quant.data_platform.audited_decision_reconciliation_silver import (
        reconciliation_context,
    )

    revisions, fingerprints = _pins()
    reconciliation = build_native_iron_condor_decision_reconciliation(
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
    )
    persist_native_iron_condor_decision_reconciliation(
        target,
        coverage_report=_coverage(),
        run_id="run-1",
        stages=("strategy", "portfolio_risk"),
        stage_revisions=revisions,
        stage_recording_fingerprints=fingerprints,
        expected_context_sha256=reconciliation_context(reconciliation),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="RECONCILIATION_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        persist_native_iron_condor_decision_reconciliation(
            target,
            coverage_report=_coverage(),
            run_id="run-1",
            stages=("strategy", "portfolio_risk"),
            stage_revisions=revisions,
            stage_recording_fingerprints=fingerprints,
            expected_context_sha256=reconciliation_context(reconciliation),
            actor_id="researcher",
            code_revision="a" * 40,
        )
