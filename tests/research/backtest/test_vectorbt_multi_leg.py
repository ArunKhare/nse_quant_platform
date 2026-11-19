"""Tests for multi-leg vectorbt portfolio modeling."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from nse_quant.research.backtest.vectorbt_multi_leg import (
    MultiLegPosition,
    multi_leg_pnl,
    run_multi_leg_vectorbt_backtest,
)


def _position():
    return MultiLegPosition(
        entry_ts=pd.Timestamp(datetime(2026, 1, 1, 9, 20, tzinfo=UTC)),
        exit_ts=pd.Timestamp(datetime(2026, 1, 1, 15, 15, tzinfo=UTC)),
        net_credit_entry=10.0,
        net_credit_exit=5.0,
        lot_size=75,
        contracts=1,
        slippage_per_leg=0.0,
        brokerage_per_lot=0.0,
        exit_reason="profit_target",
        legs=(),
    )


def test_multi_leg_pnl():
    assert multi_leg_pnl(_position()) == 375.0


def test_multi_leg_backtest():
    result = run_multi_leg_vectorbt_backtest(positions=[_position()])

    assert result["available"] is True
    assert result["multi_leg_positions"] == 1
    assert result["multi_leg_pnl"] == 375.0
    assert result["decision_eligibility_asserted"] is False
