import pytest

from nse_quant.core.models import Instrument, OptionType, OrderSide
from nse_quant.execution.kite_broker import KiteBroker, LiveTradingDisabledError


def make_proposal():
    from datetime import date

    from nse_quant.core.models import Leg, TradeProposal

    instrument = Instrument(
        tradingsymbol="NIFTY26OCT25000CE",
        instrument_token=1,
        underlying="NIFTY",
        expiry=date(2026, 10, 23),
        strike=25000,
        option_type=OptionType.CE,
        lot_size=75,
    )

    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=instrument.expiry,
        thesis="test",
        legs=[Leg(instrument=instrument, side=OrderSide.SELL, lots=1)],
        entry_limit_price=100.0,
    )


def test_kite_broker_cannot_submit():
    broker = KiteBroker()

    with pytest.raises(LiveTradingDisabledError):
        broker.submit(make_proposal())


def test_kite_broker_cannot_modify_or_cancel():
    broker = KiteBroker()

    with pytest.raises(LiveTradingDisabledError):
        broker.modify_order("order-1", {"quantity": 1})

    with pytest.raises(LiveTradingDisabledError):
        broker.cancel_order("order-1")
