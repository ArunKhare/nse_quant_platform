"""Tests for the native iron-condor decision Gold publication candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform.native_iron_condor_decision_gold import (
    gold_context,
    initialize_decision_gold,
    publish_decision_gold,
    replay_decision_gold,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY


def _gold() -> dict[str, Any]:
    return {
        "version": "native-iron-condor-decision-gold@1",
        "strategy": STRATEGY,
        "run_id": "gold-run-1",
        "reconciliation_revision_id": "a" * 64,
        "reconciliation_recording_fingerprint": "b" * 64,
        "identity_time_evidence_revision_id": "c" * 64,
        "identity_time_evidence_recording_fingerprint": "d" * 64,
        "availability_economic_evidence_revision_id": "e" * 64,
        "availability_economic_evidence_recording_fingerprint": "f" * 64,
        "coverage_revision_id": "a" * 64,
        "coverage_recording_fingerprint": "b" * 64,
        "coverage_evidence_links_context": "evidence-context",
        "authoritative_boundary_context": "boundary-context",
        "stages": [
            {
                "stage": "strategy",
                "replayed": True,
                "revision_id": "a" * 64,
                "recording_fingerprint": "b" * 64,
                "decision_eligibility_asserted": False,
            },
            {
                "stage": "portfolio_risk",
                "replayed": True,
                "revision_id": "c" * 64,
                "recording_fingerprint": "d" * 64,
                "decision_eligibility_asserted": False,
            },
        ],
        "complete": False,
        "decision_eligibility_asserted": False,
        "point_in_time_decision": False,
    }


@pytest.fixture()
def target(tmp_path: Path):
    path = tmp_path / "decision-gold.duckdb"
    with duckdb.connect(str(path)) as connection:
        initialize_decision_gold(connection)
        yield connection


def test_publishes_and_replays_gold(target) -> None:
    document = _gold()
    result = publish_decision_gold(
        target,
        document=document,
        expected_context_sha256=gold_context(document),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    assert result["decision_eligibility_asserted"] is False
    replay = replay_decision_gold(
        target,
        run_id="gold-run-1",
        expected_revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    assert replay["replayed"] is True
    assert replay["gold"] == document


def test_duplicate_gold_rejected(target) -> None:
    document = _gold()
    publish_decision_gold(
        target,
        document=document,
        expected_context_sha256=gold_context(document),
        actor_id="researcher",
        code_revision="a" * 40,
    )
    with pytest.raises(Rejected, match="DECISION_GOLD_FIRST_WRITE_OR_ORPHAN_OBLIGATION"):
        publish_decision_gold(
            target,
            document=document,
            expected_context_sha256=gold_context(document),
            actor_id="researcher",
            code_revision="a" * 40,
        )


def test_point_in_time_gold_rejected(target) -> None:
    document = _gold()
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        gold_context(document)


def test_unreplayed_stage_rejected(target) -> None:
    document = _gold()
    document["stages"][1]["replayed"] = False
    with pytest.raises(Rejected, match="DECISION_GOLD_STAGE_REPLAY_INCOMPLETE"):
        gold_context(document)
