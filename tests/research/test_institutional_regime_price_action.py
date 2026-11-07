"""Tests for the institutional regime price-action component."""

from __future__ import annotations

from nse_quant.research.institutional_regime_price_action import (
    InstitutionalRegimePriceActionSettings,
    compute_price_action,
)


def test_no_candles():
    settings = InstitutionalRegimePriceActionSettings()
    result = compute_price_action(closes=[], highs=[], lows=[], settings=settings)
    assert result["available"] is False
    assert result["state"] == "INSUFFICIENT_DATA"


def test_length_mismatch():
    settings = InstitutionalRegimePriceActionSettings()
    result = compute_price_action(closes=[1.0], highs=[1.0, 2.0], lows=[0.5], settings=settings)
    assert result["available"] is False
    assert result["reason"] == "candle_length_mismatch"


def test_trend_up():
    settings = InstitutionalRegimePriceActionSettings(range_band_pct=0.10)
    closes = [100.0, 105.0, 110.0, 115.0]
    highs = [101.0, 106.0, 111.0, 116.0]
    lows = [99.0, 104.0, 109.0, 114.0]
    result = compute_price_action(closes=closes, highs=highs, lows=lows, settings=settings)
    assert result["available"] is True
    assert result["state"] == "TREND_UP"


def test_trend_down():
    settings = InstitutionalRegimePriceActionSettings(range_band_pct=0.10)
    closes = [115.0, 110.0, 105.0, 100.0]
    highs = [116.0, 111.0, 106.0, 101.0]
    lows = [114.0, 109.0, 104.0, 99.0]
    result = compute_price_action(closes=closes, highs=highs, lows=lows, settings=settings)
    assert result["available"] is True
    assert result["state"] == "TREND_DOWN"


def test_range_upper():
    settings = InstitutionalRegimePriceActionSettings(range_band_pct=0.10)
    closes = [100.0, 102.0, 104.0, 106.0]
    highs = [101.0, 103.0, 105.0, 107.0]
    lows = [99.0, 101.0, 103.0, 105.0]
    result = compute_price_action(closes=closes, highs=highs, lows=lows, settings=settings)
    assert result["available"] is True
    assert result["state"] == "RANGE_UPPER"


def test_range_lower():
    settings = InstitutionalRegimePriceActionSettings(range_band_pct=0.10)
    closes = [106.0, 104.0, 102.0, 100.0]
    highs = [107.0, 105.0, 103.0, 101.0]
    lows = [105.0, 103.0, 101.0, 99.0]
    result = compute_price_action(closes=closes, highs=highs, lows=lows, settings=settings)
    assert result["available"] is True
    assert result["state"] == "RANGE_LOWER"


def test_range_middle():
    settings = InstitutionalRegimePriceActionSettings(range_band_pct=0.10)
    closes = [100.0, 103.0, 101.0, 103.0]
    highs = [101.0, 104.0, 102.0, 104.0]
    lows = [99.0, 102.0, 100.0, 102.0]
    result = compute_price_action(closes=closes, highs=highs, lows=lows, settings=settings)
    assert result["available"] is True
    assert result["state"] == "RANGE_MIDDLE"
