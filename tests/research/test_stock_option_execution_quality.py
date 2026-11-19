"""Tests for stock-option execution quality."""

from __future__ import annotations

import pytest

from nse_quant.research.stock_option_execution_quality import (
    ExecutionQualitySettings,
    classify_execution_quality,
    evaluate_execution_quality,
)


def test_good_execution_quality():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is True
    assert result["failures"] == []
    assert result["decision_eligibility_asserted"] is False
    assert result["spread_pct"] == pytest.approx(100.0 / 99.0 * 100.0 - 100.0)


def test_stale_quote_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=400.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is False
    assert "quote_too_stale_or_missing" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_wide_spread_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=90.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is False
    assert "spread_too_wide" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_depth_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=10,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is False
    assert "insufficient_depth" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_risk_reward_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=0.5,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is False
    assert "insufficient_risk_reward" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_high_slippage_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=1.0,
        time_to_event_days=10.0,
    )
    assert result["tradeable"] is False
    assert "slippage_too_high_or_missing" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_event_too_close_fails():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=1.0,
    )
    assert result["tradeable"] is False
    assert "event_risk_too_close_or_missing" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_classify_good():
    result = evaluate_execution_quality(
        quote_age_seconds=10.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=0.1,
        time_to_event_days=10.0,
    )
    assert classify_execution_quality(result) == "GOOD"


def test_classify_acceptable():
    result = evaluate_execution_quality(
        quote_age_seconds=400.0,
        bid=99.0,
        ask=100.0,
        depth=100,
        risk_reward_ratio=2.0,
        expected_slippage_pct=1.0,
        time_to_event_days=10.0,
    )
    assert classify_execution_quality(result) == "ACCEPTABLE"


def test_classify_poor():
    result = evaluate_execution_quality(
        quote_age_seconds=400.0,
        bid=90.0,
        ask=100.0,
        depth=10,
        risk_reward_ratio=0.5,
        expected_slippage_pct=1.0,
        time_to_event_days=1.0,
    )
    assert classify_execution_quality(result) == "POOR"


def test_settings_defaults():
    settings = ExecutionQualitySettings()
    assert settings.max_quote_age_seconds == 300.0
    assert settings.max_spread_pct == 2.0
    assert settings.min_depth == 50
    assert settings.min_risk_reward == 1.0
    assert settings.max_expected_slippage_pct == 0.5
    assert settings.max_time_to_event_days == 3.0
