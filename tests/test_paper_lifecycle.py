from datetime import UTC, datetime

import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    ExitReason,
    Instrument,
    Leg,
    OptionQuote,
    OptionType,
    OrderSide,
    StrategyPositionStatus,
    TradeProposal,
)
from nse_quant.market_data.replay_provider import ReplayMarketDataProvider


def _instrument(token: int, strike: float, option_type: OptionType) -> Instrument:
    return Instrument(
        tradingsymbol=f"NIFTY{strike}{option_type.value}",
        instrument_token=token,
        underlying="NIFTY",
        expiry=datetime.now(UTC).date(),
        strike=strike,
        option_type=option_type,
        lot_size=75,
    )


def _quote(instrument: Instrument, price: float) -> OptionQuote:
    return OptionQuote(
        instrument_token=instrument.instrument_token,
        ltp=price,
        bid=price - 0.05,
        ask=price + 0.05,
        instrument=instrument,
    )


def _proposal() -> TradeProposal:
    long_put = _instrument(1, 24000, OptionType.PE)
    short_put = _instrument(2, 24100, OptionType.PE)
    short_call = _instrument(3, 24200, OptionType.CE)
    long_call = _instrument(4, 24300, OptionType.CE)

    legs = [
        Leg(
            instrument=long_put,
            side=OrderSide.BUY,
            lots=1,
            entry_price=80.0,
        ),
        Leg(
            instrument=short_put,
            side=OrderSide.SELL,
            lots=1,
            entry_price=120.0,
        ),
        Leg(
            instrument=short_call,
            side=OrderSide.SELL,
            lots=1,
            entry_price=110.0,
        ),
        Leg(
            instrument=long_call,
            side=OrderSide.BUY,
            lots=1,
            entry_price=70.0,
        ),
    ]

    net_credit = (120.0 + 110.0 - 80.0 - 70.0) * 75

    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=datetime.now(UTC).date(),
        thesis="End-to-end lifecycle test",
        legs=legs,
        entry_limit_price=net_credit,
        target_price=net_credit * 0.5,
        stop_loss_price=net_credit * 2.0,
    )


def test_paper_lifecycle_fill_mark_exit_close(
    test_store,
    decision_loop_environment,
):
    proposal = _proposal()
    mark_snapshot = ChainSnapshot(
        underlying=proposal.underlying,
        spot=24100.0,
        expiry=proposal.expiry,
        quotes=[
            _quote(leg.instrument, price)
            for leg, price in zip(
                proposal.legs,
                [80.0, 100.0, 90.0, 70.0],
                strict=True,
            )
        ],
    )
    loop = decision_loop_environment.build_loop(
        ReplayMarketDataProvider([mark_snapshot]),
    )

    order = loop.broker.submit(proposal)

    assert order.status.value == "FILLED"

    strategy_position, leg_positions = loop._open_positions(proposal, order)

    assert strategy_position.status == StrategyPositionStatus.OPEN
    assert len(leg_positions) == 4
    assert len({leg.entry_price for leg in proposal.legs}) == 4

    loop._mark_positions(
        strategy_position=strategy_position,
        leg_positions=leg_positions,
        snapshot=mark_snapshot,
    )
    assert strategy_position.current_price == proposal.target_price
    assert strategy_position.unrealized_pnl == 3000.0

    loop._close_positions(
        proposal,
        strategy_position,
        leg_positions,
        ExitReason.TARGET_PROFIT,
    )

    persisted = loop.positions.get_open_strategy_positions()

    assert persisted == []

    row = test_store.conn.execute(
        """
        SELECT
            status,
            exit_reason,
            entry_price,
            current_price,
            realized_pnl
        FROM strategy_positions
        WHERE strategy_position_id = ?
        """,
        [strategy_position.strategy_position_id],
    ).fetchone()

    assert row is not None
    assert row[0] == "CLOSED"
    assert row[1] == "TARGET_PROFIT"
    assert row[2] == pytest.approx(6000.0)
    assert row[3] == pytest.approx(3000.0)
    assert row[4] == pytest.approx(3000.0)
