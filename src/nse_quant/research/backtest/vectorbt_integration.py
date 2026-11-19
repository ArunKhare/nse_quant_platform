"""Research-only integration between iron-condor backtests and vectorbt.

This module converts completed iron-condor backtest summaries into vectorbt
replay trades. It does not place orders, authorize execution, assert decision
eligibility, or authorize live trading.
"""

from __future__ import annotations

from typing import Any

from nse_quant.research.backtest.vectorbt_adapter import VectorbtAdapterSettings
from nse_quant.research.backtest.vectorbt_backtest import (
    BacktestTrade,
    run_vectorbt_from_completed_trades,
)
from nse_quant.research.iron_condor_backtest import BacktestTradeSummary


def iron_condor_trades_to_vectorbt(
    trades: list[BacktestTradeSummary],
    *,
    underlying: str = "NIFTY",
    strategy: str = "iron_condor_monitor",
) -> list[BacktestTrade]:
    """Convert iron-condor trade summaries into vectorbt replay trades."""
    vectorbt_trades: list[BacktestTrade] = []

    for trade in trades:
        vectorbt_trades.append(
            BacktestTrade(
                entry_ts=trade.entry_ts.to_pydatetime(),
                exit_ts=trade.exit_ts.to_pydatetime(),
                underlying=underlying,
                strategy=strategy,
                direction="short",
                size=1.0,
                entry_price=float(trade.credit_entry),
                exit_price=float(trade.credit_exit),
                exit_reason=trade.exit_reason,
                metadata={
                    "expiry": trade.expiry.isoformat(),
                    "spot_entry": trade.spot_entry,
                    "spot_exit": trade.spot_exit,
                    "iron_condor_pnl": trade.pnl,
                },
            )
        )

    return vectorbt_trades


def run_iron_condor_vectorbt_backtest(
    *,
    trades: list[BacktestTradeSummary],
    settings: VectorbtAdapterSettings | None = None,
) -> dict[str, Any]:
    """Replay iron-condor trade summaries through vectorbt."""
    vectorbt_trades = iron_condor_trades_to_vectorbt(trades)
    return run_vectorbt_from_completed_trades(
        trades=vectorbt_trades,
        settings=settings,
    )
