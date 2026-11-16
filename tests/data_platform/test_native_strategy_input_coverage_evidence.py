"""Evidence-linked native strategy input coverage derivation."""

import pytest

from nse_quant.data_platform.native_strategy_input_coverage_evidence import (
    EvidencePin,
    Rejected,
    derive_native_strategy_input_coverage,
)
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    REQUIREMENTS,
    VERSION,
)

REV = "a" * 64
FP = "b" * 64


def _pin(requirement_id: str) -> EvidencePin:
    return EvidencePin(
        requirement_id=requirement_id,
        revision_id=REV,
        recording_fingerprint=FP,
        row_count=3,
    )


def test_empty_evidence_reports_all_missing() -> None:
    report = derive_native_strategy_input_coverage()
    assert report["version"] == VERSION
    assert report["definition_sha256"] == DEFINITION_SHA256
    assert report["covered"] == []
    assert report["unlinked"] == []
    assert report["missing"] == [requirement_id for requirement_id, _s, _n in REQUIREMENTS]
    assert report["complete"] is False
    assert report["decision_eligibility_asserted"] is False
    assert report["evidence_refs"] == {}


def test_pinned_evidence_maps_to_covered() -> None:
    report = derive_native_strategy_input_coverage({"market_session": _pin("market_session")})
    assert report["covered"] == ["market_session"]
    assert report["missing"] == [
        requirement_id for requirement_id, _s, _n in REQUIREMENTS if requirement_id != "market_session"
    ]
    ref = report["evidence_refs"]["market_session"]
    assert REV in ref and FP in ref and "row_count=3" in ref
    assert report["decision_eligibility_asserted"] is False


def test_identity_requirement_never_auto_coverable() -> None:
    with pytest.raises(Rejected, match="AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE"):
        derive_native_strategy_input_coverage(
            {"authoritative_identity_and_time": _pin("authoritative_identity_and_time")}
        )


def test_unknown_requirement_rejected() -> None:
    with pytest.raises(Rejected, match="UNKNOWN_REQUIREMENT_ID"):
        derive_native_strategy_input_coverage({"not_a_requirement": _pin("not_a_requirement")})


def test_mismatched_id_rejected() -> None:
    with pytest.raises(Rejected, match="EVIDENCE_ID_MISMATCH"):
        derive_native_strategy_input_coverage(
            {
                "market_session": EvidencePin(
                    requirement_id="iv_rank_and_history",
                    revision_id=REV,
                    recording_fingerprint=FP,
                    row_count=1,
                )
            }
        )


def test_bad_revision_rejected() -> None:
    with pytest.raises(Rejected, match="EXACT_REVISION_PIN_REQUIRED"):
        EvidencePin(
            requirement_id="market_session",
            revision_id="short",
            recording_fingerprint=FP,
            row_count=1,
        )


def test_bad_fingerprint_rejected() -> None:
    with pytest.raises(Rejected, match="EXACT_RECORDING_FINGERPRINT_REQUIRED"):
        EvidencePin(
            requirement_id="market_session",
            revision_id=REV,
            recording_fingerprint="nothex",
            row_count=1,
        )


def test_non_positive_row_count_rejected() -> None:
    with pytest.raises(Rejected, match="POSITIVE_ROW_COUNT_REQUIRED"):
        EvidencePin(
            requirement_id="market_session",
            revision_id=REV,
            recording_fingerprint=FP,
            row_count=0,
        )
