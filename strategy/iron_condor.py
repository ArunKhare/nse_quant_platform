"""IV-rich iron condor monitor. Emits proposals only."""
from __future__ import annotations
from core.models import ChainSnapshot,Leg,MarketFeatures,OptionType,OrderSide,TradeProposal
from core.settings import settings
from strategy.gates import default_gate_engine

class IronCondorMonitor:
    strategy_name="iron_condor_monitor"
    def __init__(self): self.params=settings.strategy.iron_condor_monitor; self.gates=default_gate_engine()
    def evaluate(self,snapshot:ChainSnapshot,features:MarketFeatures):
        atm=snapshot.atm_strike(); w=self.params.wing_distance_points
        strikes=[(OptionType.PE,atm-2*w,OrderSide.BUY),(OptionType.PE,atm-w,OrderSide.SELL),(OptionType.CE,atm+w,OrderSide.SELL),(OptionType.CE,atm+2*w,OrderSide.BUY)]
        lookup={(q.instrument.option_type,q.instrument.strike):q for q in snapshot.quotes}
        if any(k not in lookup for k,_,_ in strikes): return None,[]
        legs=[Leg(instrument=lookup[k].instrument,side=s,lots=1) for k,_,s in strikes]
        credit=sum(lookup[k].mid or 0 for k,_,s in strikes if s==OrderSide.SELL)-sum(lookup[k].mid or 0 for k,_,s in strikes if s==OrderSide.BUY)
        if credit<self.params.min_credit: return None,[]
        if features.expected_move_points and max(atm-w-snapshot.spot,snapshot.spot-(atm+w))<features.expected_move_points*settings.analytics.max_expected_move_buffer: return None,[]
        p=TradeProposal(strategy=self.strategy_name,underlying=snapshot.underlying,expiry=snapshot.expiry,thesis=f"IV-rich range: IV rank={features.iv_rank}, IV-RV={features.iv_rv_spread}",legs=legs,entry_limit_price=round(credit,2),target_price=round(credit*.4,2),stop_loss_price=round(credit*2,2),expected_move_points=features.expected_move_points,metadata={"atm":atm,"credit":credit})
        return p,self.gates.evaluate(p,features)
