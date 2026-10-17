from datetime import UTC, date, datetime, time

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

EXPIRY = date(2026, 10, 29)


def make_instrument(
    token: int,
    strike: int,
    option_type: OptionType,
) -> Instrument:
    return Instrument(
        tradingsymbol=f"NIFTY{strike}{option_type.value}",
        instrument_token=token,
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=strike,
        option_type=option_type,
        lot_size=75,
    )


def make_iron_condor() -> TradeProposal:
    return TradeProposal(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=EXPIRY,
        thesis="Range-bound market",
        legs=[
            Leg(
                instrument=make_instrument(1, 24300, OptionType.PE),
                side=OrderSide.BUY,
                lots=1,
            ),
            Leg(
                instrument=make_instrument(2, 24500, OptionType.PE),
                side=OrderSide.SELL,
                lots=1,
            ),
            Leg(
                instrument=make_instrument(3, 25500, OptionType.CE),
                side=OrderSide.SELL,
                lots=1,
            ),
            Leg(
                instrument=make_instrument(4, 25700, OptionType.CE),
                side=OrderSide.BUY,
                lots=1,
            ),
        ],
        entry_limit_price=50.0,
        target_price=20.0,
        stop_loss_price=120.0,
    )


def make_features() -> MarketFeatures:
    return MarketFeatures(
        ts=datetime.combine(
            date(2026, 10, 22),
            time(10, 0),
            tzinfo=UTC,
        ),
        underlying="NIFTY",
        spot=25000.0,
        expiry=EXPIRY,
        liquidity_score=0.8,
    )


def test_repository_backed_risk_approves_defined_risk(tmp_path):
    store = DuckDBStore(tmp_path / "risk-approved.duckdb")
    engine = RiskEngine(store.conn)

    decision = engine.evaluate(
        make_iron_condor(),
        make_features(),
    )

    assert decision.approved
    assert decision.reasons == []

    store.close()


def test_repository_backed_risk_rejects_naked_short(tmp_path):
    store = DuckDBStore(tmp_path / "risk-naked.duckdb")
    engine = RiskEngine(store.conn)

    proposal = make_iron_condor()
    proposal.legs = [proposal.legs[1]]

    decision = engine.evaluate(
        proposal,
        make_features(),
    )

    assert not decision.approved
    assert "undefined_risk_structure" in decision.reasons

    store.close()


def test_repository_backed_risk_rejects_too_many_lots(tmp_path):
    store = DuckDBStore(tmp_path / "risk-lots.duckdb")
    engine = RiskEngine(store.conn)

    proposal = make_iron_condor()

    for leg in proposal.legs:
        leg.lots = 99

    decision = engine.evaluate(
        proposal,
        make_features(),
    )

    assert not decision.approved
    assert "max_lots_exceeded" in decision.reasons

    store.close()


def test_paper_broker_computes_leg_level_pnl(tmp_path):
    store = DuckDBStore(tmp_path / "broker-pnl.duckdb")
    broker = PaperBroker()

    proposal = make_iron_condor()
    order = broker.submit(proposal)

    assert order.status.value == "FILLED"

    position = broker.positions[0]
   
    # Initial equal allocation: 50 / 4 = 12.5 per leg.
    for leg in proposal.legs:
        assert position.leg_entry_prices[leg.instrument.instrument_token] == 12.5

    # Mark legs at their actual market prices.
    current_prices = {
        1: 20.0,  # long put: +7.5 * 75
        2: 10.0,  # short put: +(12.5 - 10) * 75
        3: 15.0,  # short call: +(12.5 - 15) * 75 * -1
        4: 25.0,  # long call: +(25 - 12.5) * 75
    }

    marked = broker.mark_position(
        position.position_id,
        current_prices,
    )

    expected_unrealized = (
        (20.0 - 12.5) * 75
        + (12.5 - 10.0) * 75
        + (12.5 - 15.0) * 75
        + (25.0 - 12.5) * 75
    )

    assert marked is not None
    assert marked.unrealized_pnl == expected_unrealized

    closed = broker.close_position(
        position.position_id,
        current_prices,
        "TARGET_PROFIT",
    )

    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.exit_reason == "TARGET_PROFIT"
    assert closed.realized_pnl == expected_unrealized
    assert closed.unrealized_pnl == 0.0

    store.close()


def test_paper_broker_rejects_invalid_price():
    broker = PaperBroker()
    proposal = make_iron_condor()
    proposal.entry_limit_price = 0.0

    order = broker.submit(proposal)

    assert order.status.value == "REJECTED"
    assert order.reject_reason == "invalid_price"