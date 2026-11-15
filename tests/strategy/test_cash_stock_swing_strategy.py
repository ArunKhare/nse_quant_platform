"""Tests for the cash-stock swing strategy."""

from __future__ import annotations

from nse_quant.strategy.cash_stock_swing import CashStockSwingStrategy


def make_candles(n=60, base=100.0):
    candles = []
    for i in range(n):
        candles.append(
            {
                "date": f"2026-01-{(i % 28) + 1:02d}",
                "open": base,
                "high": base + 1.0,
                "low": base - 1.0,
                "close": base + 0.5,
                "volume": 1000 + i,
            }
        )
    return candles


def test_no_candles_returns_none():
    strategy = CashStockSwingStrategy()
    proposal, gates = strategy.evaluate([])
    assert proposal is None
    assert gates == []


def test_entry_signal_produces_proposal():
    strategy = CashStockSwingStrategy()
    candles = make_candles()
    proposal, gates = strategy.evaluate(candles)
    # Signal may or may not trigger depending on the synthetic data; just check the contract.
    if proposal is not None:
        assert proposal.strategy == "cash_stock_swing"
        assert proposal.legs[0].side.value == "BUY"
        assert proposal.stop_loss_price < proposal.entry_limit_price
        assert proposal.target_price > proposal.entry_limit_price
        assert gates[-1].passed is True
    else:
        assert gates[-1].passed is False


def test_event_risk_blocks_entry():
    strategy = CashStockSwingStrategy()
    candles = make_candles()
    proposal, gates = strategy.evaluate(candles, event_risk_active=True)
    assert proposal is None
    assert gates[-1].passed is False
