from datetime import date,datetime,time,timezone
from core.models import Instrument,Leg,MarketFeatures,OptionType,OrderSide,TradeProposal
from execution.paper_broker import PaperBroker
from risk.risk_engine import RiskEngine

def proposal():
    exp=date(2026,10,29); legs=[]
    for token,strike,kind,side in [(1,24300,OptionType.PE,OrderSide.BUY),(2,24500,OptionType.PE,OrderSide.SELL),(3,25500,OptionType.CE,OrderSide.SELL),(4,25700,OptionType.CE,OrderSide.BUY)]:
        legs.append(Leg(instrument=Instrument(f"NIFTY{strike}{kind.value}",token,"NIFTY",exp,strike,kind,75),side=side,lots=1))
    return TradeProposal(strategy="iron_condor_monitor",underlying="NIFTY",expiry=exp,thesis="test",legs=legs,entry_limit_price=50)

def features():
    return MarketFeatures(ts=datetime.combine(date(2026,10,22),time(10,0),tzinfo=timezone.utc),underlying="NIFTY",spot=25000,expiry=date(2026,10,29),liquidity_score=.8)

def test_risk_and_paper_fill():
    p=proposal(); assert RiskEngine().evaluate(p,features()).approved
    assert PaperBroker().submit(p).status.value=="FILLED"

def test_daily_loss_blocks():
    r=RiskEngine(); r.daily_realized_pnl=-999999
    d=r.evaluate(proposal(),features()); assert not d.approved and "daily_loss_limit" in d.reasons
