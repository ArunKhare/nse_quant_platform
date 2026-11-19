"""Tests for stock-option liquidity thresholds."""

from __future__ import annotations

import pytest

from nse_quant.research.stock_option_liquidity import (
    LiquidityThresholds,
    classify_liquidity,
    evaluate_liquidity,
)


def test_liquid_option_passes():
    result = evaluate_liquidity(bid=99.0, ask=100.0, depth=100, open_interest=5000, volume=500)
    assert result["tradable"] is True
    assert result["failures"] == []
    assert result["decision_eligibility_asserted"] is False
    assert result["spread_pct"] == pytest.approx(100.0 / 99.0 * 100.0 - 100.0)


def test_wide_spread_fails():
    result = evaluate_liquidity(bid=90.0, ask=100.0, depth=100, open_interest=5000, volume=500)
    assert result["tradable"] is False
    assert "spread_too_wide" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_depth_fails():
    result = evaluate_liquidity(bid=99.0, ask=100.0, depth=10, open_interest=5000, volume=500)
    assert result["tradable"] is False
    assert "insufficient_depth" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_oi_fails():
    result = evaluate_liquidity(bid=99.0, ask=100.0, depth=100, open_interest=100, volume=500)
    assert result["tradable"] is False
    assert "insufficient_open_interest" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_volume_fails():
    result = evaluate_liquidity(bid=99.0, ask=100.0, depth=100, open_interest=5000, volume=10)
    assert result["tradable"] is False
    assert "insufficient_volume" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_missing_quote_fails():
    result = evaluate_liquidity(bid=None, ask=None, depth=100, open_interest=5000, volume=500)
    assert result["tradable"] is False
    assert "missing_or_invalid_quote" in result["failures"]
    assert result["decision_eligibility_asserted"] is False


def test_classify_liquid():
    result = evaluate_liquidity(bid=99.0, ask=100.0, depth=100, open_interest=5000, volume=500)
    assert classify_liquidity(result) == "LIQUID"


def test_classify_marginal():
    result = evaluate_liquidity(bid=90.0, ask=100.0, depth=100, open_interest=5000, volume=500)
    assert classify_liquidity(result) == "MARGINAL"


def test_classify_illiquid():
    result = evaluate_liquidity(bid=None, ask=None, depth=10, open_interest=100, volume=10)
    assert classify_liquidity(result) == "ILLIQUID"


def test_settings_defaults():
    settings = LiquidityThresholds()
    assert settings.max_spread_pct == 2.0
    assert settings.min_depth == 50
    assert settings.min_oi == 1000
    assert settings.min_volume == 100
