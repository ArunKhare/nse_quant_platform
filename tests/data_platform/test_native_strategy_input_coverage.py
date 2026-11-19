"""Native strategy input coverage reconciliation; observational only."""

import pytest

from nse_quant.data_platform.native_strategy_input_coverage import (
    InputCoverage,
    Rejected,
    reconcile_native_strategy_input_coverage,
)
from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    REQUIREMENTS,
    STAGES,
    STRATEGY,
    VERSION,
)


def _covered(requirement_id: str) -> InputCoverage:
    return InputCoverage(
        requirement_id=requirement_id,
        status="covered",
        evidence_ref=f"silver://{requirement_id}",
    )


def test_empty_coverage_reports_all_missing() -> None:
    report = reconcile_native_strategy_input_coverage()
    assert report["version"] == VERSION
    assert report["strategy"] == STRATEGY
    assert report["definition_sha256"] == DEFINITION_SHA256
    assert report["stages"] == STAGES
    assert report["covered"] == []
    assert report["unlinked"] == []
    assert report["missing"] == [requirement_id for requirement_id, _s, _n in REQUIREMENTS]
    assert report["complete"] is False
    assert report["decision_eligibility_asserted"] is False


def test_partial_coverage_partitions_exact_ids() -> None:
    first, second, *_rest = [requirement_id for requirement_id, _s, _n in REQUIREMENTS]
    report = reconcile_native_strategy_input_coverage(
        {
            first: _covered(first),
            second: InputCoverage(requirement_id=second, status="unlinked", evidence_ref=None),
        }
    )
    assert report["covered"] == [first]
    assert report["unlinked"] == [second]
    assert report["missing"] == [
        requirement_id for requirement_id, _s, _n in REQUIREMENTS if requirement_id not in (first, second)
    ]
    assert report["complete"] is False
    assert report["decision_eligibility_asserted"] is False


def test_identity_requirement_never_auto_coverable() -> None:
    with pytest.raises(Rejected, match="AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE"):
        reconcile_native_strategy_input_coverage(
            {
                "authoritative_identity_and_time": InputCoverage(
                    requirement_id="authoritative_identity_and_time",
                    status="covered",
                    evidence_ref="silver://identity",
                )
            }
        )


def test_unknown_requirement_rejected() -> None:
    with pytest.raises(Rejected, match="UNKNOWN_REQUIREMENT_ID"):
        reconcile_native_strategy_input_coverage({"not_a_requirement": _covered("not_a_requirement")})


def test_covered_requires_evidence() -> None:
    with pytest.raises(Rejected, match="COVERED_INPUT_EVIDENCE_REQUIRED"):
        InputCoverage(requirement_id="market_session", status="covered", evidence_ref=None)


def test_uncovered_forbids_evidence() -> None:
    with pytest.raises(Rejected, match="UNCOVERED_INPUT_EVIDENCE_FORBIDDEN"):
        InputCoverage(
            requirement_id="market_session",
            status="missing",
            evidence_ref="silver://market_session",
        )


def test_mismatched_id_rejected() -> None:
    with pytest.raises(Rejected, match="COVERAGE_ID_MISMATCH"):
        reconcile_native_strategy_input_coverage(
            {
                "market_session": InputCoverage(
                    requirement_id="iv_rank_and_history",
                    status="covered",
                    evidence_ref="silver://iv",
                )
            }
        )
