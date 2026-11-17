"""Native iron-condor decision-run reconciliation persistence.

Persists the reconciliation between a recorded/replayed native iron-condor
decision run and the current Silver-backed coverage report. Exact replay is
supported. No eligibility, live trading, healing, backfill, adoption, or
execution authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_reconciliation import (
    reconcile_audited_decision_run,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    VERSION as RECONCILIATION_SILVER_VERSION,
)
from nse_quant.data_platform.audited_decision_reconciliation_silver import (
    record_audited_decision_reconciliation,
    replay_audited_decision_reconciliation,
)
from nse_quant.data_platform.native_strategy_requirements import (
    STRATEGY,
)


def build_native_iron_condor_decision_reconciliation(
    *,
    coverage_report: dict[str, Any],
    run_id: str,
    stages: tuple[str, ...],
    stage_revisions: dict[str, str],
    stage_recording_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Build a reconciliation document for persisted reconciliation Silver."""
    reconciliation = reconcile_audited_decision_run(
        coverage_report=coverage_report,
        run_id=run_id,
        stages=stages,
        stage_revisions=stage_revisions,
        stage_recording_fingerprints=stage_recording_fingerprints,
    )
    return {
        "version": RECONCILIATION_SILVER_VERSION,
        "strategy": STRATEGY,
        "run_id": run_id,
        "coverage_revision_id": reconciliation["coverage"]["revision_id"],
        "coverage_recording_fingerprint": reconciliation["coverage"]["recording_fingerprint"],
        "coverage": reconciliation["coverage"],
        "stages": reconciliation["stages"],
        "complete": reconciliation["complete"],
        "decision_eligibility_asserted": False,
    }


def persist_native_iron_condor_decision_reconciliation(
    target: Any,
    *,
    coverage_report: dict[str, Any],
    run_id: str,
    stages: tuple[str, ...],
    stage_revisions: dict[str, str],
    stage_recording_fingerprints: dict[str, str],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Build, record, and exactly replay a reconciliation for one decision run."""
    reconciliation = build_native_iron_condor_decision_reconciliation(
        coverage_report=coverage_report,
        run_id=run_id,
        stages=stages,
        stage_revisions=stage_revisions,
        stage_recording_fingerprints=stage_recording_fingerprints,
    )
    recorded = record_audited_decision_reconciliation(
        target,
        reconciliation=reconciliation,
        expected_context_sha256=expected_context_sha256,
        actor_id=actor_id,
        code_revision=code_revision,
    )
    replay = replay_audited_decision_reconciliation(
        target,
        run_id=run_id,
        expected_revision_id=recorded["revision_id"],
        expected_recording_fingerprint=recorded["recording_fingerprint"],
    )
    return {
        "run_id": run_id,
        "reconciliation": reconciliation,
        "recording": recorded,
        "replay": replay,
        "decision_eligibility_asserted": False,
    }
