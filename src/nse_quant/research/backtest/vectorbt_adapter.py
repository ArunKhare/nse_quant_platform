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
    """Replay completed historical trades through vectorbt.

    Each trade must provide entry_ts, exit_ts, size, entry_price, and
    exit_price. This function uses supplied historical prices and does not
    authorize execution.
    """
    settings = settings or VectorbtAdapterSettings()

    if not trades:
        return {
            "available": False,
            "reason": "no_trades",
            "decision_eligibility_asserted": False,
        }

    timestamps = sorted({trade["entry_ts"] for trade in trades} | {trade["exit_ts"] for trade in trades})
    index = pd.DatetimeIndex(timestamps)

    entries = pd.Series(False, index=index, dtype=bool)
    exits = pd.Series(False, index=index, dtype=bool)
    prices = pd.Series(float("nan"), index=index, dtype=float)

    for trade in trades:
        entries.loc[trade["entry_ts"]] = True
        exits.loc[trade["exit_ts"]] = True
        prices.loc[trade["entry_ts"]] = float(trade["entry_price"])
        prices.loc[trade["exit_ts"]] = float(trade["exit_price"])

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
    stats = portfolio.stats()

    return {
        "available": True,
        "trade_count": len(trades),
        "total_return": float(stats["Total Return [%]"]) / 100.0,
        "max_drawdown": float(stats["Max Drawdown [%]"]) / 100.0,
        "sharpe_ratio": (float(stats["Sharpe Ratio"]) if "Sharpe Ratio" in stats else None),
        "equity_curve": [
            {
                "ts": timestamp.isoformat(),
                "equity": float(value),
            }
            for timestamp, value in equity.items()
        ],
        "decision_eligibility_asserted": False,
    }
