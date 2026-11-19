"""Silver-backed coverage with option-chain mapping."""

import pytest

from nse_quant.data_platform.native_strategy_input_coverage_evidence import (
    EvidencePin,
    Rejected,
)
from nse_quant.data_platform.native_strategy_input_coverage_silver import (
    MAPPINGS,
    UNMAPPED,
    derive_silver_backed_coverage,
    observe_silver_coverage,
)

REV = "a" * 64
FP = "b" * 64


def _pins() -> dict[str, EvidencePin]:
    return observe_silver_coverage(
        underlying_iv_revision_id=REV,
        underlying_iv_fingerprint=FP,
        underlying_iv_row_count=3,
        daily_rv_revision_id=REV,
        daily_rv_fingerprint=FP,
        daily_rv_row_count=2,
        spot_features_revision_id=REV,
        spot_features_fingerprint=FP,
        spot_features_row_count=4,
        regime_policy_revision_id=REV,
        regime_policy_fingerprint=FP,
        regime_policy_row_count=1,
        market_events_revision_id=REV,
        market_events_fingerprint=FP,
        market_events_row_count=5,
        option_chain_revision_id=REV,
        option_chain_fingerprint=FP,
        option_chain_row_count=2,
    )


def test_mapped_requirements_covered_unmapped_missing() -> None:
    report = derive_silver_backed_coverage(_pins())
    assert set(report["covered"]) == {requirement_id for requirement_id, _source in MAPPINGS}
    assert len(report["covered"]) == len(MAPPINGS)
    assert report["missing"] == list(UNMAPPED)
    assert report["unlinked"] == []
    assert report["complete"] is False
    assert report["decision_eligibility_asserted"] is False


def test_identity_requirement_never_auto_coverable() -> None:
    with pytest.raises(Rejected, match="UNKNOWN_SILVER_BACKED_REQUIREMENT"):
        derive_silver_backed_coverage(
            {
                "authoritative_identity_and_time": EvidencePin(
                    requirement_id="authoritative_identity_and_time",
                    revision_id=REV,
                    recording_fingerprint=FP,
                    row_count=1,
                )
            }
        )


def test_unknown_requirement_rejected() -> None:
    pins = _pins()
    pins["not_a_requirement"] = EvidencePin(
        requirement_id="not_a_requirement",
        revision_id=REV,
        recording_fingerprint=FP,
        row_count=1,
    )
    with pytest.raises(Rejected, match="UNKNOWN_SILVER_BACKED_REQUIREMENT"):
        derive_silver_backed_coverage(pins)
