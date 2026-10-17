from datetime import UTC, date, datetime, time

from nse_quant.core.models import (
    Instrument,
    Leg,
    MarketFeatures,
    OptionType,
    OrderSide,
    StrategyPosition,
    StrategyPositionStatus,
    TradeProposal,
)
from nse_quant.execution.broker import PaperBroker
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import PositionRepository
from nse_quant.risk.risk_engine import RiskEngine


def proposal():
    exp=date(2026,10,29);
    legs=[]
    for token,strike,kind,side in [(1,24300,OptionType.PE,OrderSide.BUY),(2,24500,OptionType.PE,OrderSide.SELL),(3,25500,OptionType.CE,OrderSide.SELL),(4,25700,OptionType.CE,OrderSide.BUY)]:
        legs.append(Leg(instrument=Instrument(tradingsymbol=f"NIFTY{strike}{kind.value}",instrument_token=token,underlying="NIFTY",expiry=exp,strike=strike,option_type=kind,lot_size=75),side=side,lots=1))
    return TradeProposal(strategy="iron_condor_monitor",underlying="NIFTY",expiry=exp,thesis="test",legs=legs,entry_limit_price=50)

def features():
    return MarketFeatures(ts=datetime.combine(date(2026,10,22),time(10,0),tzinfo=UTC),underlying="NIFTY",spot=25000,expiry=date(2026,10,29),liquidity_score=.8)

def test_risk_and_paper_fill(tmp_path):
    """Verify the proposal passes risk checks and fills in the paper broker."""
    store = DuckDBStore(tmp_path / "risk.duckdb")
    p=proposal();
    assert RiskEngine(conn=store.conn).evaluate(p,features()).approved
    assert PaperBroker().submit(p).status.value=="FILLED"
    store.close()

def test_daily_loss_blocks(tmp_path):
    store = DuckDBStore(tmp_path / "risk.duckdb")
    position = StrategyPosition(
        proposal_id="closed-trade",
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=date(2026, 10, 29),
        opened_at=datetime.now(UTC),
        entry_price=50,
        realized_pnl=-999999,
        status=StrategyPositionStatus.CLOSED,
        closed_at=datetime.now(UTC),
    )
    PositionRepository(store.conn).create_strategy_position(position)

    d=RiskEngine(conn=store.conn).evaluate(proposal(),features());
    assert not d.approved and "daily_loss_limit" in d.reasons
    store.close()
