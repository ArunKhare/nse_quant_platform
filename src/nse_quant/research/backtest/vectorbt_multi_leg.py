"""Research-only multi-leg vectorbt portfolio modeling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from nse_quant.research.backtest.vectorbt_adapter import VectorbtAdapterSettings
from nse_quant.research.backtest.vectorbt_backtest import (
    VectorbtBacktestRequest,
    run_vectorbt_backtest,
)


@dataclass(frozen=True)
class MultiLegPosition:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    net_credit_entry: float
    net_credit_exit: float
    lot_size: int
    contracts: int
    slippage_per_leg: float
    brokerage_per_lot: float
    exit_reason: str
    legs: tuple[dict[str, float | str], ...]


def multi_leg_pnl(position: MultiLegPosition) -> float:
    entry_credit = position.net_credit_entry - 4 * position.slippage_per_leg
    exit_credit = position.net_credit_exit + 4 * position.slippage_per_leg
    gross = (entry_credit - exit_credit) * position.lot_size * position.contracts
    brokerage = position.brokerage_per_lot * position.lot_size * position.contracts
    return float(gross - brokerage)


def run_multi_leg_vectorbt_backtest(
    *,
    positions: list[MultiLegPosition],
    settings: VectorbtAdapterSettings | None = None,
) -> dict[str, Any]:
    settings = settings or VectorbtAdapterSettings()

    if not positions:
        return {
            "available": False,
            "reason": "no_positions",
            "decision_eligibility_asserted": False,
        }

    timestamps = sorted({position.entry_ts for position in positions} | {position.exit_ts for position in positions})
    index = pd.DatetimeIndex(timestamps)

    entries = pd.Series(False, index=index, dtype=bool)
    exits = pd.Series(False, index=index, dtype=bool)
    prices = pd.Series(float("nan"), index=index, dtype=float)

    for position in positions:
        entries.loc[position.entry_ts] = True
        exits.loc[position.exit_ts] = True
        prices.loc[position.entry_ts] = position.net_credit_entry
        prices.loc[position.exit_ts] = position.net_credit_exit

    prices = prices.ffill()

    if prices.isna().any():
        return {
            "available": False,
            "reason": "incomplete_multi_leg_prices",
            "decision_eligibility_asserted": False,
        }

    request = VectorbtBacktestRequest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        prices=prices,
        entries=entries,
        exits=exits,
        settings=settings,
    )

    result = run_vectorbt_backtest(request)
    result["multi_leg_positions"] = len(positions)
    result["multi_leg_pnl"] = sum(multi_leg_pnl(position) for position in positions)
    result["legs"] = [list(position.legs) for position in positions]
    return result
