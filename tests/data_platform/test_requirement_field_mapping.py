"""Tests for requirement-to-candidate-field mapping."""

from __future__ import annotations

from nse_quant.data_platform.requirement_field_mapping import (
    REQUIREMENT_FIELD_CANDIDATES,
    map_requirements_to_fields,
)


def _candidate_with_all():
    fields = []
    for candidates in REQUIREMENT_FIELD_CANDIDATES.values():
        fields.extend(candidates)
    return {field: "value" for field in set(fields)}


def test_all_mapped():
    result = map_requirements_to_fields(candidate=_candidate_with_all())
    assert result["mapped"] is True
    assert result["reason"] == "ALL_REQUIREMENTS_MAPPED"
    assert result["unmapped"] == []
    assert all(len(v) > 0 for v in result["mapping"].values())


def test_partial_mapping():
    candidate = _candidate_with_all()
    del candidate["iv_rank"]
    del candidate["iv_history"]
    del candidate["observation_count"]
    result = map_requirements_to_fields(candidate=candidate)
    assert result["mapped"] is False
    assert result["reason"] == "UNMAPPED_REQUIREMENTS_REMAIN"
    assert "iv_rank_and_history" in result["unmapped"]
    assert result["mapping"]["iv_rank_and_history"] == []


def test_result_json_nested_mapping():
    candidate = dict(
        result_json='{"iv_rank": "x", "iv_rv_spread": "y", "expected_move_points": 1.0}',
    )
    result = map_requirements_to_fields(candidate=candidate)
    assert "iv_rank_and_history" in result["mapping"]
    assert result["mapping"]["iv_rank_and_history"] == ["iv_rank"]
    assert result["mapping"]["iv_rv_spread"] == ["iv_rv_spread"]
    assert result["mapping"]["expected_move"] == ["expected_move_points"]
    assert result["mapped"] is False


def test_empty_candidate_all_unmapped():
    result = map_requirements_to_fields(candidate=dict())
    assert result["mapped"] is False
    assert result["reason"] == "UNMAPPED_REQUIREMENTS_REMAIN"
    assert set(result["unmapped"]) == set(REQUIREMENT_FIELD_CANDIDATES)
    assert all(v == [] for v in result["mapping"].values())


def test_non_dict_refused():
    result = map_requirements_to_fields(candidate="not_a_dict")
    assert result["mapped"] is False
    assert result["reason"] == "CANDIDATE_OBJECT_REQUIRED"
    assert set(result["unmapped"]) == set(REQUIREMENT_FIELD_CANDIDATES)
