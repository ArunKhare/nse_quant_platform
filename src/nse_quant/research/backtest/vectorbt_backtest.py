"""Deterministic, research-only vectorbt backtesting for NIFTY strategies.

This module evaluates historical strategy behavior. It does not place orders,
authorize execution, assert decision eligibility, or authorize live trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
import vectorbt as vbt

from nse_quant.research.backtest.vectorbt_adapter import (
    VectorbtAdapterSettings,
)


@dataclass(frozen=True)
class BacktestTrade:
    entry_ts: datetime
    exit_ts: datetime
    underlying: str
    strategy: str
    direction: str
    size: float
    entry_price: float
    exit_price: float
    fees: float = 0.0
    slippage: float = 0.0
    exit_reason: str = "strategy_exit"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorbtBacktestRequest:
    strategy: str
    underlying: str
    prices: pd.Series
    entries: pd.Series
    exits: pd.Series
    settings: VectorbtAdapterSettings = VectorbtAdapterSettings()
    direction: str = "long"


def _validate_request(request: VectorbtBacktestRequest) -> None:
    if request.strategy != "iron_condor_monitor":
        raise ValueError("UNSUPPORTED_BACKTEST_STRATEGY")

    if request.underlying != "NIFTY":
        raise ValueError("UNSUPPORTED_BACKTEST_UNDERLYING")

    if request.direction not in {"long", "short"}:
        raise ValueError("UNSUPPORTED_BACKTEST_DIRECTION")

    if request.prices.empty or request.entries.empty or request.exits.empty:
        raise ValueError("BACKTEST_INPUT_EMPTY")

    if not request.prices.index.equals(request.entries.index):
        raise ValueError("BACKTEST_INDEX_MISMATCH")

    if not request.prices.index.equals(request.exits.index):
        raise ValueError("BACKTEST_INDEX_MISMATCH")

    if request.prices.isna().any():
        raise ValueError("BACKTEST_PRICE_MISSING")

    if not request.entries.dtype == bool or not request.exits.dtype == bool:
        raise ValueError("BACKTEST_SIGNAL_TYPE_INVALID")


def _metrics(portfolio: vbt.Portfolio) -> dict[str, Any]:
    stats = portfolio.stats()

    return {
        "total_return": float(stats["Total Return [%]"]) / 100.0,
        "max_drawdown": float(stats["Max Drawdown [%]"]) / 100.0,
        "sharpe_ratio": (float(stats["Sharpe Ratio"]) if "Sharpe Ratio" in stats else None),
        "trade_count": int(stats["Total Trades"]) if "Total Trades" in stats else 0,
        "win_rate": (float(stats["Win Rate [%]"]) / 100.0 if "Win Rate [%]" in stats else None),
    }


def run_vectorbt_backtest(
    request: VectorbtBacktestRequest,
) -> dict[str, Any]:
    """Run a deterministic research-only vectorbt backtest."""
    _validate_request(request)

    portfolio = vbt.Portfolio.from_signals(
        request.prices,
        request.entries,
        request.exits,
        init_cash=request.settings.initial_capital,
        fees=request.settings.fees,
        slippage=request.settings.slippage,
        direction=request.direction,
    )

    equity = portfolio.value()
    metrics = _metrics(portfolio)

    return {
        "available": True,
        "strategy": request.strategy,
        "underlying": request.underlying,
        "direction": request.direction,
        "initial_capital": request.settings.initial_capital,
        "fees": request.settings.fees,
        "slippage": request.settings.slippage,
        "equity_curve": [
            {
                "ts": timestamp.isoformat(),
                "equity": float(value),
            }
            for timestamp, value in equity.items()
        ],
        **metrics,
        "decision_eligibility_asserted": False,
    }


def run_vectorbt_from_completed_trades(
    *,
    trades: list[BacktestTrade],
    settings: VectorbtAdapterSettings | None = None,
) -> dict[str, Any]:
    """Replay completed historical trades through vectorbt.

    This function uses supplied historical entry and exit prices. It does not
    synthesize prices and does not authorize execution.
    """
    settings = settings or VectorbtAdapterSettings()

    if not trades:
        return {
            "available": False,
            "reason": "no_trades",
            "decision_eligibility_asserted": False,
        }

    timestamps = sorted({trade.entry_ts for trade in trades} | {trade.exit_ts for trade in trades})
    index = pd.DatetimeIndex(timestamps)

    entries = pd.Series(False, index=index, dtype=bool)
    exits = pd.Series(False, index=index, dtype=bool)
    prices = pd.Series(float("nan"), index=index, dtype=float)

    for trade in trades:
        entries.loc[trade.entry_ts] = True
        exits.loc[trade.exit_ts] = True
        prices.loc[trade.entry_ts] = trade.entry_price
        prices.loc[trade.exit_ts] = trade.exit_price

    prices = prices.ffill()

    if prices.isna().any():
        return {
            "available": False,
            "reason": "incomplete_trade_prices",
            "decision_eligibility_asserted": False,
        }

    portfolio = vbt.Portfolio.from_signals(
        prices,
        entries,
        exits,
        init_cash=settings.initial_capital,
        fees=settings.fees,
        slippage=settings.slippage,
    )

    equity = portfolio.value()
    metrics = _metrics(portfolio)

    return {
        "available": True,
        "trade_count": len(trades),
        "equity_curve": [
            {
                "ts": timestamp.isoformat(),
                "equity": float(value),
            }
            for timestamp, value in equity.items()
        ],
        **metrics,
        "decision_eligibility_asserted": False,
    }
