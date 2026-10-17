from datetime import UTC, datetime, timedelta

from nse_quant.core.models import (
    Instrument,
    Leg,
    MarketFeatures,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.risk.risk_engine import RiskEngine


def make_proposal(lots: int = 1):
    expiry = datetime.now(UTC).date() + timedelta(days=5)

    instrument = Instrument(
        tradingsymbol="NIFTY26OCT25000CE",
        instrument_token=1,
        underlying="NIFTY",
        expiry=expiry,
        strike=25000,
        option_type=OptionType.CE,
        lot_size=75,
    )

    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=expiry,
        thesis="test",
        legs=[Leg(instrument=instrument, side=OrderSide.SELL, lots=lots)],
        entry_limit_price=100.0,
    )


def make_features():
    return MarketFeatures(
        ts=datetime.now(UTC),
        underlying="NIFTY",
        spot=25000,
        expiry=datetime.now(UTC).date() + timedelta(days=5),
    )


def test_risk_rejects_too_many_lots(tmp_path):
    store = DuckDBStore(tmp_path / "risk.duckdb")
    engine = RiskEngine(store.conn)

    decision = engine.evaluate(make_proposal(lots=99), make_features())

    assert not decision.approved
    assert "max_lots_exceeded" in decision.reasons

    store.close()


def test_risk_rejects_naked_short(tmp_path):
    store = DuckDBStore(tmp_path / "risk.duckdb")
    engine = RiskEngine(store.conn)

    decision = engine.evaluate(make_proposal(), make_features())

    assert not decision.approved
    assert "undefined_risk_structure" in decision.reasons

    store.close()