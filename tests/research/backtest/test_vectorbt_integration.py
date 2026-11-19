"""Tests for iron-condor vectorbt integration."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from nse_quant.research.backtest.vectorbt_integration import (
    iron_condor_trades_to_vectorbt,
)
from nse_quant.research.iron_condor_backtest import BacktestTradeSummary


def test_converts_iron_condor_trade_summary():
    trade = BacktestTradeSummary(
        entry_ts=pd.Timestamp(datetime(2026, 1, 1, 9, 20, tzinfo=UTC)),
        exit_ts=pd.Timestamp(datetime(2026, 1, 1, 15, 15, tzinfo=UTC)),
        expiry=pd.Timestamp("2026-01-08").date(),
        spot_entry=100.0,
        spot_exit=101.0,
        credit_entry=10.0,
        credit_exit=5.0,
        pnl=375.0,
        exit_reason="profit_target",
    )

    trades = iron_condor_trades_to_vectorbt([trade])

    assert len(trades) == 1
    assert trades[0].strategy == "iron_condor_monitor"
    assert trades[0].direction == "short"
    assert trades[0].entry_price == 10.0
    assert trades[0].exit_price == 5.0
    assert trades[0].metadata["iron_condor_pnl"] == 375.0
