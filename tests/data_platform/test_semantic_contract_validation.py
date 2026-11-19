"""Tests for semantic contract validation."""

from __future__ import annotations

from nse_quant.data_platform.semantic_contract_validation import (
    SEMANTIC_CONTRACTS,
    validate_semantic_contracts,
)


def _valid_candidate():
    return dict(
        iv_rank=50.0,
        observation_count=100,
        cold_start_policy="reject",
        iv_rv_spread=0.05,
        expected_move_points=10.0,
        oi=1000,
        volume=500,
        spread=0.01,
    )


def test_all_contracts_satisfied():
    result = validate_semantic_contracts(candidate=_valid_candidate())
    assert result["valid"] is True
    assert result["reason"] == "ALL_SEMANTIC_CONTRACTS_SATISFIED"
    assert result["violations"] == dict()


def test_missing_field_violation():
    candidate = _valid_candidate()
    del candidate["iv_rank"]
    result = validate_semantic_contracts(candidate=candidate)
    assert result["valid"] is False
    assert result["reason"] == "SEMANTIC_CONTRACT_VIOLATIONS"
    assert "MISSING_FIELD:iv_rank" in result["violations"]["iv_rank_and_history"]


def test_invalid_value_violation():
    candidate = _valid_candidate()
    candidate["expected_move_points"] = -1.0
    result = validate_semantic_contracts(candidate=candidate)
    assert result["valid"] is False
    assert result["reason"] == "SEMANTIC_CONTRACT_VIOLATIONS"
    assert "INVALID_VALUE:expected_move_points" in result["violations"]["expected_move"]


def test_invalid_cold_start_violation():
    candidate = _valid_candidate()
    candidate["cold_start_policy"] = "invalid"
    result = validate_semantic_contracts(candidate=candidate)
    assert result["valid"] is False
    assert result["reason"] == "SEMANTIC_CONTRACT_VIOLATIONS"
    assert "INVALID_VALUE:cold_start_policy" in result["violations"]["iv_rank_and_history"]


def test_empty_candidate_all_violations():
    result = validate_semantic_contracts(candidate=dict())
    assert result["valid"] is False
    assert result["reason"] == "SEMANTIC_CONTRACT_VIOLATIONS"
    assert set(result["violations"]) == set(SEMANTIC_CONTRACTS)


def test_non_dict_refused():
    result = validate_semantic_contracts(candidate="not_a_dict")
    assert result["valid"] is False
    assert result["reason"] == "CANDIDATE_OBJECT_REQUIRED"
