"""Tests for the cash-stock swing strategy signal generator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nse_quant.research.cash_stock_swing import (
    CashStockSwingSettings,
    compute_atr,
    compute_rvol,
    compute_sma,
    generate_signal,
)


def _candles(n: int = 250, trend: float = 0.002, seed: int = 42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = 100 * np.cumprod(1 + rng.normal(trend, 0.01, n))
    high = close * 1.01
    low = close * 0.99
    open_ = close * 0.995
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_compute_sma_basic():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    sma = compute_sma(series, 3)
    assert sma.iloc[-1] == 4.0
    assert sma.iloc[:2].isna().all()


def test_compute_atr_basic():
    high = pd.Series([10.0, 11.0, 12.0])
    low = pd.Series([9.0, 10.0, 11.0])
    close = pd.Series([9.5, 10.5, 11.5])
    atr = compute_atr(high, low, close, period=2)
    assert atr.iloc[-1] > 0


def test_compute_rvol_basic():
    volume = pd.Series([100.0] * 30 + [200.0])
    rvol = compute_rvol(volume, baseline_periods=30)
    assert rvol.iloc[-1] == 2.0


def test_generate_signal_insufficient_history():
    candles = _candles(100)
    result = generate_signal(candles=candles)
    assert result["available"] is False
    assert result["reason"] == "insufficient_history"
    assert result["decision_eligibility_asserted"] is False


def test_generate_signal_missing_columns():
    candles = _candles(250).drop(columns=["volume"])
    result = generate_signal(candles=candles)
    assert result["available"] is False
    assert result["reason"] == "missing_candle_columns"
    assert result["decision_eligibility_asserted"] is False


def test_generate_signal_uptrend_breakout():
    candles = _candles(250, trend=0.005)
    result = generate_signal(candles=candles)
    assert result["available"] is True
    assert result["decision_eligibility_asserted"] is False
    assert "entry_signal" in result
    assert "stop_price" in result and "target_price" in result
    assert result["stop_price"] < result["entry_price"] < result["target_price"]


def test_generate_signal_event_filter_blocks_entry():
    candles = _candles(250, trend=0.005)
    result = generate_signal(candles=candles, event_risk_active=True)
    assert result["available"] is True
    assert result["event_filter_active"] is True
    assert result["entry_signal"] is False
    assert result["decision_eligibility_asserted"] is False


def test_settings_defaults():
    settings = CashStockSwingSettings()
    assert settings.sma_short == 50
    assert settings.sma_long == 200
    assert settings.breakout_days == 20
    assert settings.rvol_threshold == 1.5
    assert settings.atr_period == 14
    assert settings.stop_atr_multiple == 2.0
    assert settings.target_r_multiple == 2.0
    assert settings.time_stop_days == 10
    assert settings.min_history == 220
