"""End-to-end smoke tests for paper execution."""

from datetime import UTC, date, datetime, time, timedelta

from nse_quant.core.models import (
    Instrument,
    Leg,
    MarketFeatures,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.execution.broker import PaperBroker
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.risk.risk_engine import RiskEngine


def test_end_to_end(tmp_path):
    store = DuckDBStore(tmp_path / "smoke.duckdb")
    expiry = date.today() + timedelta(days=5)
    legs = [
        Leg(
            instrument=Instrument(
                tradingsymbol=f"NIFTY{strike}{option_type.value}",
                instrument_token=token,
                underlying="NIFTY",
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=75,
            ),
            side=side,
            lots=1,
        )
        for token, strike, option_type, side in [
            (1, 24300, OptionType.PE, OrderSide.BUY),
            (2, 24500, OptionType.PE, OrderSide.SELL),
            (3, 25500, OptionType.CE, OrderSide.SELL),
            (4, 25700, OptionType.CE, OrderSide.BUY),
        ]
    ]
    proposal = TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=expiry,
        thesis="Range-bound market",
        legs=legs,
        entry_limit_price=50.0,
    )
    features = MarketFeatures(
        ts=datetime.combine(expiry - timedelta(days=1), time(10), tzinfo=UTC),
        underlying="NIFTY",
        spot=25000.0,
        expiry=expiry,
        liquidity_score=0.8,
    )

    try:
        assert RiskEngine(store.conn).evaluate(proposal, features).approved
        assert PaperBroker().submit(proposal).status.value == "FILLED"
    finally:
        store.close()
