"""Tests for native strategy coverage evidence-link validation."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_strategy_coverage_evidence_links import (
    coverage_evidence_links_context,
    validate_coverage_evidence_links,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _coverage() -> dict[str, Any]:
    return {
        "covered": ["market_session", "iv_rank_and_history"],
        "evidence_refs": {
            "market_session": (
                "silver://market_session?revision_id="
                + "a" * 64
                + "&recording_fingerprint="
                + "b" * 64
                + "&row_count=1"
            ),
            "iv_rank_and_history": (
                "silver://iv_rank_and_history?revision_id="
                + "c" * 64
                + "&recording_fingerprint="
                + "d" * 64
                + "&row_count=2"
            ),
        },
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_validates_coverage_evidence_links() -> None:
    coverage = _coverage()
    result = validate_coverage_evidence_links(coverage)
    assert result["valid"] is True
    assert result["covered_count"] == 2
    assert result["decision_eligibility_asserted"] is False
    assert coverage_evidence_links_context(coverage)


def test_point_in_time_decision_rejected() -> None:
    coverage = _coverage()
    coverage["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_coverage_evidence_links(coverage)


def test_missing_evidence_ref_rejected() -> None:
    coverage = _coverage()
    del coverage["evidence_refs"]["iv_rank_and_history"]
    with pytest.raises(Rejected, match="COVERAGE_EVIDENCE_REF_MISSING"):
        validate_coverage_evidence_links(coverage)


def test_invalid_fingerprint_rejected() -> None:
    coverage = _coverage()
    coverage["evidence_refs"]["market_session"] = (
        "silver://market_session?revision_id=" + "a" * 64 + "&recording_fingerprint=short&row_count=1"
    )
    with pytest.raises(Rejected, match="COVERAGE_EVIDENCE_FINGERPRINT_INVALID"):
        validate_coverage_evidence_links(coverage)


def test_requirement_mismatch_rejected() -> None:
    coverage = _coverage()
    coverage["evidence_refs"]["market_session"] = (
        "silver://other_requirement?revision_id=" + "a" * 64 + "&recording_fingerprint=" + "b" * 64 + "&row_count=1"
    )
    with pytest.raises(Rejected, match="COVERAGE_EVIDENCE_REF_REQUIREMENT_MISMATCH"):
        validate_coverage_evidence_links(coverage)
