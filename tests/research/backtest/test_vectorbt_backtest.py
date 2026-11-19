"""Tests for deterministic vectorbt backtesting."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from nse_quant.research.backtest.vectorbt_adapter import (
    VectorbtAdapterSettings,
)
from nse_quant.research.backtest.vectorbt_backtest import (
    BacktestTrade,
    VectorbtBacktestRequest,
    run_vectorbt_backtest,
    run_vectorbt_from_completed_trades,
)


def _index():
    return pd.DatetimeIndex(
        [
            datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
        ]
    )


def test_rejects_unsupported_strategy():
    request = VectorbtBacktestRequest(
        strategy="unsupported",
        underlying="NIFTY",
        prices=pd.Series([100.0, 101.0, 102.0], index=_index()),
        entries=pd.Series([True, False, False], index=_index()),
        exits=pd.Series([False, False, True], index=_index()),
    )

    with pytest.raises(ValueError, match="UNSUPPORTED_BACKTEST_STRATEGY"):
        run_vectorbt_backtest(request)


def test_rejects_unsupported_underlying():
    request = VectorbtBacktestRequest(
        strategy="iron_condor_monitor",
        underlying="BANKNIFTY",
        prices=pd.Series([100.0, 101.0, 102.0], index=_index()),
        entries=pd.Series([True, False, False], index=_index()),
        exits=pd.Series([False, False, True], index=_index()),
    )

    with pytest.raises(ValueError, match="UNSUPPORTED_BACKTEST_UNDERLYING"):
        run_vectorbt_backtest(request)


def test_rejects_index_mismatch():
    request = VectorbtBacktestRequest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        prices=pd.Series([100.0, 101.0, 102.0], index=_index()),
        entries=pd.Series([True, False], index=_index()[:-1]),
        exits=pd.Series([False, False, True], index=_index()),
    )

    with pytest.raises(ValueError, match="BACKTEST_INDEX_MISMATCH"):
        run_vectorbt_backtest(request)


def test_runs_deterministic_backtest():
    request = VectorbtBacktestRequest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        prices=pd.Series([100.0, 101.0, 102.0], index=_index()),
        entries=pd.Series([True, False, False], index=_index()),
        exits=pd.Series([False, False, True], index=_index()),
        settings=VectorbtAdapterSettings(
            initial_capital=1_000_000.0,
            fees=0.0,
            slippage=0.0,
        ),
    )

    first = run_vectorbt_backtest(request)
    second = run_vectorbt_backtest(request)

    assert first["available"] is True
    assert first["strategy"] == "iron_condor_monitor"
    assert first["underlying"] == "NIFTY"
    assert first["decision_eligibility_asserted"] is False
    assert first == second


def test_completed_trades_use_real_prices():
    entry = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    exit_time = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)

    result = run_vectorbt_from_completed_trades(
        trades=[
            BacktestTrade(
                entry_ts=entry,
                exit_ts=exit_time,
                underlying="NIFTY",
                strategy="iron_condor_monitor",
                direction="short",
                size=1.0,
                entry_price=100.0,
                exit_price=105.0,
            )
        ],
        settings=VectorbtAdapterSettings(
            initial_capital=1_000_000.0,
            fees=0.0,
            slippage=0.0,
        ),
    )

    assert result["available"] is True
    assert result["trade_count"] == 1
    assert result["decision_eligibility_asserted"] is False
    assert result["total_return"] > 0.0
