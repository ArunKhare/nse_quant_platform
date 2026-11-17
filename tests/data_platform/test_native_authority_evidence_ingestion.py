"""Tests for native authority evidence ingestion."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_authority_evidence_ingestion import (
    audit_authority_evidence,
    ingest_authority_evidence,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(kind: str, obligation: str) -> dict[str, object]:
    return {
        "version": "native-authority-evidence-ingestion@1",
        "evidence": {
            "kind": kind,
            "source_authority": "accepted_authority",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "obligation": obligation,
        "duplicate": False,
        "healed": False,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_ingests_identity_time_evidence() -> None:
    result = ingest_authority_evidence(_document("identity_time", "original_first_write"))
    assert result["recorded"] is True
    assert result["evidence_kind"] == "identity_time"
    assert result["obligation"] == "original_first_write"
    assert result["decision_eligibility_asserted"] is False


def test_ingests_availability_evidence() -> None:
    result = ingest_authority_evidence(_document("availability", "original_first_write"))
    assert result["recorded"] is True
    assert result["evidence_kind"] == "availability"
    assert result["decision_eligibility_asserted"] is False


def test_ingests_economic_validity_evidence() -> None:
    result = ingest_authority_evidence(_document("economic_validity", "original_first_write"))
    assert result["recorded"] is True
    assert result["evidence_kind"] == "economic_validity"
    assert result["decision_eligibility_asserted"] is False


def test_rejects_duplicate() -> None:
    document = _document("identity_time", "original_first_write")
    document["duplicate"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_DUPLICATE"):
        ingest_authority_evidence(document)


def test_rejects_point_in_time_decision() -> None:
    document = _document("identity_time", "original_first_write")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        ingest_authority_evidence(document)


def test_audits_without_healing() -> None:
    result = audit_authority_evidence(_document("identity_time", "audit"))
    assert result["audited"] is True
    assert result["healed"] is False
    assert result["decision_eligibility_asserted"] is False


def test_rejects_healing() -> None:
    document = _document("identity_time", "final_audit")
    document["healed"] = True
    with pytest.raises(Rejected, match="AUTHORITY_EVIDENCE_HEALING_FORBIDDEN"):
        audit_authority_evidence(document)
