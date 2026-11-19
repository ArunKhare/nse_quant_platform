"""Tests for native authority evidence replay and audit integration."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_authority_evidence_replay_audit import (
    replay_authority_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(kind: str, obligation: str) -> dict[str, object]:
    return {
        "version": "native-authority-evidence-replay-audit@1",
        "evidence": {
            "kind": kind,
            "source_authority": "accepted_authority",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "obligation": obligation,
        "healed": False,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_replays_identity_time_original_first_write() -> None:
    result = replay_authority_evidence(_document("identity_time", "original_first_write"))
    assert result["replayed"] is True
    assert result["evidence_kind"] == "identity_time"
    assert result["audit_integrated"] is False
    assert result["orphan_check_integrated"] is False
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_replays_availability_audit() -> None:
    result = replay_authority_evidence(_document("availability", "audit"))
    assert result["replayed"] is True
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is False
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_replays_economic_validity_orphan_check() -> None:
    result = replay_authority_evidence(_document("economic_validity", "orphan_check"))
    assert result["replayed"] is True
    assert result["audit_integrated"] is False
    assert result["orphan_check_integrated"] is True
    assert result["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


def test_replays_economic_validity_final_audit() -> None:
    result = replay_authority_evidence(_document("economic_validity", "final_audit"))
    assert result["replayed"] is True
    assert result["audit_integrated"] is True
    assert result["orphan_check_integrated"] is False
    assert result["final_audit_integrated"] is True
    assert result["decision_eligibility_asserted"] is False


def test_rejects_point_in_time_decision() -> None:
    document = _document("identity_time", "audit")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        replay_authority_evidence(document)


def test_rejects_healing() -> None:
    document = _document("identity_time", "final_audit")
    document["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        replay_authority_evidence(document)


def test_rejects_invalid_obligation() -> None:
    document = _document("identity_time", "invalid")
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_OBLIGATION_INVALID"):
        replay_authority_evidence(document)
