"""Tests for requirements-vs-candidate coverage reconciliation."""

from __future__ import annotations

from nse_quant.data_platform.requirements_candidate_coverage import (
    REQUIRED_NAMES,
    reconcile_requirements_coverage,
)


def _candidate_with_all():
    return {name: "value" for name in REQUIRED_NAMES}


def test_all_covered():
    result = reconcile_requirements_coverage(candidate=_candidate_with_all())
    assert result["reconciled"] is True
    assert result["reason"] == "ALL_REQUIREMENTS_COVERED"
    assert result["uncovered"] == []
    assert len(result["covered"]) == len(REQUIRED_NAMES)


def test_partial_coverage():
    candidate = _candidate_with_all()
    del candidate["iv_rank_and_history"]
    result = reconcile_requirements_coverage(candidate=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "UNCOVERED_REQUIREMENTS_REMAIN"
    assert "iv_rank_and_history" in result["uncovered"]
    assert "iv_rank_and_history" not in result["covered"]


def test_result_json_nested_coverage():
    candidate = dict(
        result_json='{"iv_rank_and_history": "x", "iv_rv_spread": "y"}',
    )
    result = reconcile_requirements_coverage(candidate=candidate)
    assert "iv_rank_and_history" in result["covered"]
    assert "iv_rv_spread" in result["covered"]
    assert result["reconciled"] is False


def test_empty_candidate_all_uncovered():
    result = reconcile_requirements_coverage(candidate=dict())
    assert result["reconciled"] is False
    assert result["reason"] == "UNCOVERED_REQUIREMENTS_REMAIN"
    assert set(result["uncovered"]) == set(REQUIRED_NAMES)
    assert result["covered"] == []


def test_non_dict_refused():
    result = reconcile_requirements_coverage(candidate="not_a_dict")
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_OBJECT_REQUIRED"
    assert set(result["uncovered"]) == set(REQUIRED_NAMES)
