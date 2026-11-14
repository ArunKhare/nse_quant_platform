"""vectorbt backtest adapter; research-only bridge, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import vectorbt as vbt


@dataclass(frozen=True)
class VectorbtAdapterSettings:
    initial_capital: float = 1_000_000.0
    fees: float = 0.0
    slippage: float = 0.0


def equity_curve_to_series(equity_curve: list[dict[str, Any]]) -> pd.Series:
    """Convert a BacktestResult.equity_curve list into a pandas Series indexed by ts."""
    if not equity_curve:
        return pd.Series(dtype=float)
    index = pd.DatetimeIndex([point["ts"] for point in equity_curve])
    values = [float(point["equity"]) for point in equity_curve]
    return pd.Series(values, index=index, dtype=float)


def run_vectorbt_from_equity_curve(
    *,
    equity_curve: list[dict[str, Any]],
    settings: VectorbtAdapterSettings | None = None,
) -> dict[str, Any]:
    """Build a vectorbt Portfolio from an equity curve and return research metrics.

    This is a research-only adapter: it does not place orders, authorize
    execution, or assert decision eligibility.
    """
    settings = settings or VectorbtAdapterSettings()
    equity = equity_curve_to_series(equity_curve)
    if equity.empty:
        return {
            "available": False,
            "reason": "empty_equity_curve",
            "decision_eligibility_asserted": False,
        }
    portfolio = vbt.Portfolio.from_holding(
        equity,
        init_cash=settings.initial_capital,
        fees=settings.fees,
        slippage=settings.slippage,
    )
    stats = portfolio.stats()
    return {
        "available": True,
        "total_return": float(stats["Total Return [%]"]) / 100.0,
        "max_drawdown": float(stats["Max Drawdown [%]"]) / 100.0,
        "sharpe_ratio": float(stats["Sharpe Ratio"]) if "Sharpe Ratio" in stats else None,
        "decision_eligibility_asserted": False,
    }


def run_vectorbt_from_trades(
    *,
    trades: list[dict[str, Any]],
    settings: VectorbtAdapterSettings | None = None,
) -> dict[str, Any]:
    """Build a vectorbt Portfolio from a list of trade dicts (entry/exit ts, size, price).

    Each trade dict must have: entry_ts, exit_ts, size (positive for long), entry_price, exit_price.
    This is a research-only adapter: it does not place orders, authorize
    execution, or assert decision eligibility.
    """
    settings = settings or VectorbtAdapterSettings()
    if not trades:
        return {
            "available": False,
            "reason": "no_trades",
            "decision_eligibility_asserted": False,
        }
    entries = pd.Series(
        [True] + [False] * (len(trades) - 1),
        index=pd.DatetimeIndex([t["entry_ts"] for t in trades]),
    )
    exits = pd.Series(
        [False] * (len(trades) - 1) + [True],
        index=pd.DatetimeIndex([t["exit_ts"] for t in trades]),
    )
    # Build a simple price series spanning entry to exit for each trade (synthetic, research-only)
    all_ts = sorted({t["entry_ts"] for t in trades} | {t["exit_ts"] for t in trades})
    price_index = pd.DatetimeIndex(all_ts)
    prices = pd.Series(1.0, index=price_index)  # placeholder; real usage would map actual prices
    portfolio = vbt.Portfolio.from_signals(
        prices,
        entries,
        exits,
        init_cash=settings.initial_capital,
        fees=settings.fees,
        slippage=settings.slippage,
    )
    stats = portfolio.stats()
    return {
        "available": True,
        "total_return": float(stats["Total Return [%]"]) / 100.0,
        "max_drawdown": float(stats["Max Drawdown [%]"]) / 100.0,
        "sharpe_ratio": float(stats["Sharpe Ratio"]) if "Sharpe Ratio" in stats else None,
        "decision_eligibility_asserted": False,
    }
