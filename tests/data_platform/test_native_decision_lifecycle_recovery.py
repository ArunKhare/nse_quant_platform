"""Tests for native decision lifecycle-recovery observations."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform.native_decision_lifecycle_recovery import (
    initialize_lifecycle_recovery_silver,
    record_lifecycle_recovery,
    recovery_context,
    replay_lifecycle_recovery,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _recovery() -> dict[str, object]:
    return {
        "version": "native-decision-lifecycle-recovery@1",
        "strategy": STRATEGY,
        "run_id": "recovery-run-1",
        "recovery_id": "recovery-run-1",
        "original_obligation": {
            "status": "failed",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "recovery_attempt": {
            "outcome": "observed",
            "revision_id": "c" * 64,
            "recording_fingerprint": "d" * 64,
        },
        "healed": False,
        "adopted": False,
        "backfilled": False,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "lifecycle-recovery.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_lifecycle_recovery_silver(connection)
        yield connection


def test_records_and_replays_recovery(target) -> None:
    recovery = _recovery()
    result = record_lifecycle_recovery(
        target,
        recovery=recovery,
        expected_context_sha256=recovery_context(recovery),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["healed"] is False
    assert result["adopted"] is False
    assert result["backfilled"] is False
    replay = replay_lifecycle_recovery(
        target,
        recovery_id="recovery-run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["recovery"] == recovery


def test_duplicate_recovery_rejected(target) -> None:
    recovery = _recovery()
    record_lifecycle_recovery(
        target,
        recovery=recovery,
        expected_context_sha256=recovery_context(recovery),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="LIFECYCLE_RECOVERY_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        record_lifecycle_recovery(
            target,
            recovery=recovery,
            expected_context_sha256=recovery_context(recovery),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_healing_rejected(target) -> None:
    recovery = _recovery()
    recovery["healed"] = True
    with pytest.raises(Rejected, match="LIFECYCLE_RECOVERY_HEALING_FORBIDDEN"):
        recovery_context(recovery)


def test_adoption_rejected(target) -> None:
    recovery = _recovery()
    recovery["adopted"] = True
    with pytest.raises(Rejected, match="LIFECYCLE_RECOVERY_ADOPTION_FORBIDDEN"):
        recovery_context(recovery)


def test_backfill_rejected(target) -> None:
    recovery = _recovery()
    recovery["backfilled"] = True
    with pytest.raises(Rejected, match="LIFECYCLE_RECOVERY_BACKFILL_FORBIDDEN"):
        recovery_context(recovery)
