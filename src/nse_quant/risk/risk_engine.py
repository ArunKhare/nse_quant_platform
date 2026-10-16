"""Independent risk controls using centralized settings."""
from __future__ import annotations
from core.models import GateResult,MarketFeatures,RiskDecision,TradeProposal
from core.settings import settings

class RiskEngine:
    def __init__(self): self.limits=settings.risk; self.daily_realized_pnl=0.0; self.open_positions:list[dict]=[]
    def evaluate(self,p:TradeProposal,f:MarketFeatures,quote_lookup:dict|None=None)->RiskDecision:
        checks=[]; reasons=[]
        lots=max(l.lots for l in p.legs); checks.append(GateResult("max_lots",lots<=self.limits.max_lots_per_order,f"lots={lots}"))
        if lots>self.limits.max_lots_per_order: reasons.append("max_lots_exceeded")
        checks.append(GateResult("open_positions",len(self.open_positions)<self.limits.max_open_positions,f"open={len(self.open_positions)}"))
        if len(self.open_positions)>=self.limits.max_open_positions: reasons.append("max_open_positions")
        notional=sum(abs(l.quantity) for l in p.legs)*f.spot/10; checks.append(GateResult("notional",notional<=self.limits.max_notional_exposure,f"notional={notional:.0f}"))
        if notional>self.limits.max_notional_exposure: reasons.append("max_notional_exposure")
        checks.append(GateResult("daily_loss",self.daily_realized_pnl>-self.limits.max_daily_loss,f"pnl={self.daily_realized_pnl:.0f}"))
        if self.daily_realized_pnl<=-self.limits.max_daily_loss: reasons.append("daily_loss_limit")
        if quote_lookup:
            for leg in p.legs:
                q=quote_lookup.get((leg.instrument.option_type.value,leg.instrument.strike)); spread=getattr(q,"spread_pct",None); oi=getattr(q,"oi",None) or 0; vol=getattr(q,"volume",None) or 0
                ok=spread is not None and spread<=self.limits.max_spread_pct and oi>=self.limits.min_oi and vol>=self.limits.min_volume
                checks.append(GateResult(f"leg_{leg.instrument.tradingsymbol}",ok,f"spread={spread},oi={oi},volume={vol}"))
                if not ok: reasons.append(f"leg_liquidity_{leg.instrument.tradingsymbol}")
        return RiskDecision(not reasons,reasons,checks)
    def register_fill(self,p:TradeProposal,price:float): self.open_positions.append({"proposal_id":p.proposal_id,"entry":price})
    def register_close(self,pid:str,pnl:float):
        self.daily_realized_pnl+=pnl; self.open_positions=[x for x in self.open_positions if x["proposal_id"]!=pid]
