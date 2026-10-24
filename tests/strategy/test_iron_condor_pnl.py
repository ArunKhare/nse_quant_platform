from datetime import UTC, datetime

from nse_quant.core.models import (
    Instrument,
    Leg,
    OptionQuote,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.execution.broker import PaperBroker


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
        thesis="test",
        legs=legs,
        entry_limit_price=net_credit,
        target_price=net_credit * 0.5,
        stop_loss_price=net_credit * 2.0,
    )


def test_legs_use_distinct_entry_premiums():
    proposal = _proposal()
    premiums = [leg.entry_price for leg in proposal.legs]

    assert len(set(premiums)) == 4
    assert proposal.entry_limit_price == 6000.0


def test_paper_position_initial_mark_equals_net_credit():
    broker = PaperBroker()
    proposal = _proposal()

    order = broker.submit(proposal)
    position = broker.positions()[0]

    assert order.status.value == "FILLED"
    assert position.entry_price == 6000.0
    assert position.current_price == 6000.0
    assert position.unrealized_pnl == 0.0


def test_marking_lower_short_premiums_creates_profit():
    broker = PaperBroker()
    proposal = _proposal()
    broker.submit(proposal)
    position = broker.positions()[0]

    current_prices = {
        1: 80.0,
        2: 100.0,
        3: 90.0,
        4: 70.0,
    }

    marked = broker.mark_position(position.position_id, current_prices)

    assert marked is not None

    expected_remaining_credit = (100.0 + 90.0 - 80.0 - 70.0) * 75
    expected_pnl = 6000.0 - expected_remaining_credit

    assert marked.current_price == expected_remaining_credit
    assert marked.unrealized_pnl == expected_pnl
    assert marked.unrealized_pnl > 0
