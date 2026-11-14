"""Tests for the vectorbt backtest adapter."""

from __future__ import annotations

from datetime import UTC, datetime

from nse_quant.research.backtest.vectorbt_adapter import (
    VectorbtAdapterSettings,
    equity_curve_to_series,
    run_vectorbt_from_equity_curve,
    run_vectorbt_from_trades,
)


def _ts(minute: int):
    return datetime(2026, 1, 1, 9, minute, tzinfo=UTC)


def test_equity_curve_to_series_empty():
    series = equity_curve_to_series([])
    assert series.empty


def test_equity_curve_to_series_roundtrip():
    curve = [
        {"ts": _ts(0), "equity": 1_000_000.0},
        {"ts": _ts(1), "equity": 1_001_000.0},
    ]
    series = equity_curve_to_series(curve)
    assert len(series) == 2
    assert series.iloc[0] == 1_000_000.0
    assert series.iloc[1] == 1_001_000.0


def test_run_vectorbt_from_equity_curve_empty():
    result = run_vectorbt_from_equity_curve(equity_curve=[])
    assert result["available"] is False
    assert result["reason"] == "empty_equity_curve"
    assert result["decision_eligibility_asserted"] is False


def test_run_vectorbt_from_equity_curve_basic():
    curve = [
        {"ts": _ts(0), "equity": 1_000_000.0},
        {"ts": _ts(1), "equity": 1_010_000.0},
    ]
    result = run_vectorbt_from_equity_curve(equity_curve=curve)
    assert result["available"] is True
    assert result["decision_eligibility_asserted"] is False
    assert "total_return" in result and "max_drawdown" in result


def test_run_vectorbt_from_trades_empty():
    result = run_vectorbt_from_trades(trades=[])
    assert result["available"] is False
    assert result["reason"] == "no_trades"
    assert result["decision_eligibility_asserted"] is False


def test_run_vectorbt_from_trades_basic():
    trades = [
        {
            "entry_ts": _ts(0),
            "exit_ts": _ts(5),
            "size": 1.0,
            "entry_price": 100.0,
            "exit_price": 105.0,
        }
    ]
    result = run_vectorbt_from_trades(trades=trades)
    assert result["available"] is True
    assert result["decision_eligibility_asserted"] is False
    assert "total_return" in result and "max_drawdown" in result


def test_settings_defaults():
    settings = VectorbtAdapterSettings()
    assert settings.initial_capital == 1_000_000.0
    assert settings.fees == 0.0
    assert settings.slippage == 0.0
