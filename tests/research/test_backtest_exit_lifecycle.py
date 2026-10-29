from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    ExitReason,
    Instrument,
    Leg,
    MarketFeatures,
    OptionQuote,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.portfolio import BacktestPortfolio, BacktestTrade

EXPIRY = date(2026, 10, 30)
ENTRY_TS = datetime(2026, 10, 26, 4, 15, tzinfo=UTC)  # 09:45 IST
NEXT_TS = ENTRY_TS + timedelta(minutes=1)


def make_instrument(strike: float, option_type: OptionType) -> Instrument:
    return Instrument(
        tradingsymbol=f"NIFTY{EXPIRY:%Y%m%d}{int(strike)}{option_type.value}",
        instrument_token=int(strike) + (100 if option_type == OptionType.CE else 200),
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=strike,
        option_type=option_type,
        lot_size=1,
    )


def make_quote(
    strike: float,
    option_type: OptionType,
    price: float,
    ts: datetime,
) -> OptionQuote:
    instrument = make_instrument(strike, option_type)
    return OptionQuote(
        instrument_token=instrument.instrument_token,
        instrument=instrument,
        ltp=price,
        bid=price - 0.5,
        ask=price + 0.5,
        volume=1000,
        oi=1000,
        iv=15.0,
        received_at=ts,
    )


def make_snapshot(
    ts: datetime,
    spot: float,
    prices: dict[tuple[float, OptionType], float],
) -> ChainSnapshot:
    return ChainSnapshot(
        ts=ts,
        underlying="NIFTY",
        spot=spot,
        expiry=EXPIRY,
        quotes=[
            make_quote(strike, option_type, price, ts)
            for (strike, option_type), price in prices.items()
        ],
    )


def make_features(
    ts: datetime,
    spot: float,
    atm_iv: float = 15.0,
    expected_move_points: float = 100.0,
) -> MarketFeatures:
    return MarketFeatures(
        ts=ts,
        underlying="NIFTY",
        spot=spot,
        expiry=EXPIRY,
        atm_iv=atm_iv,
        expected_move_points=expected_move_points,
    )


def make_proposal(
    target_price: float | None = 10.0,
    stop_loss_price: float | None = 60.0,
    expiry: date = EXPIRY,
) -> TradeProposal:
    return TradeProposal(
        strategy="IRON_CONDOR",
        underlying="NIFTY",
        expiry=expiry,
        thesis="Deterministic backtest fixture",
        legs=[
            Leg(
                instrument=make_instrument(23200, OptionType.CE),
                side=OrderSide.SELL,
                lots=1,
                entry_price=50.0,
            ),
            Leg(
                instrument=make_instrument(23300, OptionType.CE),
                side=OrderSide.BUY,
                lots=1,
                entry_price=20.0,
            ),
        ],
        entry_limit_price=30.0,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        expected_move_points=100.0,
        metadata={"net_credit": 30.0},
    )


def make_portfolio() -> BacktestPortfolio:
    config = BacktestConfig(
        start_date=ENTRY_TS.date(),
        end_date=ENTRY_TS.date(),
        iv_collapse_pct=20.0,
        expected_move_buffer=1.25,
    )
    portfolio = BacktestPortfolio(initial_capital=1_000_000.0, config=config)
    return portfolio


def open_trade(
    portfolio: BacktestPortfolio,
    proposal: TradeProposal | None = None,
) -> BacktestTrade:
    proposal = proposal or make_proposal()
    entry_snapshot = make_snapshot(
        ENTRY_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 50.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    entry_features = make_features(ENTRY_TS, 23000.0)

    return portfolio.open_position(
        proposal=proposal,
        snapshot=entry_snapshot,
        features=entry_features,
        slippage_pct=0.0,
    )


def test_iv_collapse_exit_triggers():
    portfolio = make_portfolio()
    trade = open_trade(portfolio)

    exit_snapshot = make_snapshot(
        NEXT_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 40.0,
            (23300.0, OptionType.CE): 16.0,
        },
    )
    exit_features = make_features(
        NEXT_TS,
        23000.0,
        atm_iv=11.0,
        expected_move_points=100.0,
    )

    portfolio.mark_to_market(exit_snapshot, exit_features)
    exit_reason = portfolio.evaluate_exit(
        trade=trade,
        snapshot=exit_snapshot,
        features=exit_features,
    )

    assert exit_reason is not None
    assert exit_reason.value == ExitReason.IV_COLLAPSE


def test_expected_move_violation_exit_triggers():
    portfolio = make_portfolio()
    trade = open_trade(portfolio)

    exit_snapshot = make_snapshot(
        NEXT_TS,
        23300.0,
        {
            (23200.0, OptionType.CE): 50.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    exit_features = make_features(
        NEXT_TS,
        23300.0,
        atm_iv=15.0,
        expected_move_points=100.0,
    )

    portfolio.mark_to_market(exit_snapshot, exit_features)
    exit_reason = portfolio.evaluate_exit(
        trade=trade,
        snapshot=exit_snapshot,
        features=exit_features,
    )

    assert exit_reason is not None
    assert exit_reason.value == ExitReason.EXPECTED_MOVE_VIOLATION


def test_expiry_force_close_triggers():
    portfolio = make_portfolio()
    proposal = make_proposal(expiry=ENTRY_TS.date())
    trade = open_trade(portfolio, proposal=proposal)

    exit_snapshot = make_snapshot(
        NEXT_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 50.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    exit_features = make_features(NEXT_TS, 23000.0)

    portfolio.mark_to_market(exit_snapshot, exit_features)
    exit_reason = portfolio.evaluate_exit(
        trade=trade,
        snapshot=exit_snapshot,
        features=exit_features,
    )

    assert exit_reason is not None
    assert exit_reason.value == ExitReason.EXPIRY_FORCE_CLOSE


def test_no_exit_on_entry_snapshot():
    portfolio = make_portfolio()
    trade = open_trade(portfolio)

    entry_snapshot = make_snapshot(
        ENTRY_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 50.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    entry_features = make_features(ENTRY_TS, 23000.0)

    portfolio.mark_to_market(entry_snapshot, entry_features)

    assert trade.exit_debit == 0.0
    assert trade.realized_pnl == 0.0
    assert (
        portfolio.evaluate_exit(
            trade=trade,
            snapshot=entry_snapshot,
            features=entry_features,
        )
        is None
    )


def test_target_profit_requires_positive_pnl():
    portfolio = make_portfolio()
    trade = open_trade(portfolio)

    exit_snapshot = make_snapshot(
        NEXT_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 30.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    exit_features = make_features(NEXT_TS, 23000.0)

    portfolio.mark_to_market(exit_snapshot, exit_features)
    exit_reason = portfolio.evaluate_exit(
        trade=trade,
        snapshot=exit_snapshot,
        features=exit_features,
    )

    assert exit_reason is not None
    assert exit_reason.value == ExitReason.TARGET_PROFIT
    assert trade.realized_pnl > 0.0
    assert trade.realized_pnl == pytest.approx(20.0)


def test_stop_loss_requires_negative_pnl():
    portfolio = make_portfolio()
    trade = open_trade(portfolio)

    exit_snapshot = make_snapshot(
        NEXT_TS,
        23000.0,
        {
            (23200.0, OptionType.CE): 80.0,
            (23300.0, OptionType.CE): 20.0,
        },
    )
    exit_features = make_features(NEXT_TS, 23000.0)

    portfolio.mark_to_market(exit_snapshot, exit_features)
    exit_reason = portfolio.evaluate_exit(
        trade=trade,
        snapshot=exit_snapshot,
        features=exit_features,
    )

    assert exit_reason is not None
    assert exit_reason.value == ExitReason.STOP_LOSS
    assert trade.realized_pnl < 0.0
    assert trade.realized_pnl == pytest.approx(-30.0)
