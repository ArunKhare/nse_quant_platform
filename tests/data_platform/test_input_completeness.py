"""Tests for input completeness validation."""

from __future__ import annotations

from nse_quant.data_platform.input_completeness import (
    REQUIRED_KEYS,
    validate_input_completeness,
)


def _all_inputs():
    return {key: "value" for key in REQUIRED_KEYS}


def test_all_inputs_present_complete():
    result = validate_input_completeness(supplied_inputs=_all_inputs())
    assert result["complete"] is True
    assert result["reason"] == "ALL_REQUIRED_INPUTS_PRESENT"
    assert result["missing"] == []
    assert len(result["present"]) == len(REQUIRED_KEYS)


def test_missing_input_refused():
    inputs = _all_inputs()
    del inputs["iv_rank_and_history"]
    result = validate_input_completeness(supplied_inputs=inputs)
    assert result["complete"] is False
    assert result["reason"] == "MISSING_REQUIRED_INPUTS"
    assert "iv_rank_and_history" in result["missing"]
    assert "iv_rank_and_history" not in result["present"]


def test_multiple_missing_refused():
    inputs = _all_inputs()
    del inputs["iv_rank_and_history"]
    del inputs["expected_move"]
    result = validate_input_completeness(supplied_inputs=inputs)
    assert result["complete"] is False
    assert set(result["missing"]) == {"iv_rank_and_history", "expected_move"}


def test_empty_inputs_all_missing():
    result = validate_input_completeness(supplied_inputs=dict())
    assert result["complete"] is False
    assert result["reason"] == "MISSING_REQUIRED_INPUTS"
    assert set(result["missing"]) == set(REQUIRED_KEYS)
    assert result["present"] == []


def test_non_dict_refused():
    result = validate_input_completeness(supplied_inputs="not_a_dict")
    assert result["complete"] is False
    assert result["reason"] == "SUPPLIED_INPUTS_OBJECT_REQUIRED"
    assert set(result["missing"]) == set(REQUIRED_KEYS)
