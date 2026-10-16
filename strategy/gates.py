"""Pre-trade gates using YAML-backed settings."""
from __future__ import annotations
from core.models import GateResult,MarketFeatures,TradeProposal
from core.settings import settings

class Gate:
    name="base"
    def evaluate(self,p:TradeProposal,f:MarketFeatures)->GateResult: raise NotImplementedError

class MarketContextGate(Gate):
    name="market_context"
    def __init__(self,allowed:set[str]): self.allowed=allowed
    def evaluate(self,p,f):
        ok=f.regime.value in self.allowed; return GateResult(self.name,ok,f"regime={f.regime.value}",{"regime":f.regime.value})

class VolatilityGate(Gate):
    name="volatility_pricing"
    def evaluate(self,p,f):
        a=settings.analytics; ok=f.iv_rank is not None and f.iv_rank>=a.min_iv_rank and f.iv_rv_spread is not None and f.iv_rv_spread>=a.min_iv_rv_spread
        return GateResult(self.name,ok,f"iv_rank={f.iv_rank},spread={f.iv_rv_spread}",{"iv_rank":f.iv_rank,"iv_rv_spread":f.iv_rv_spread})

class LiquidityGate(Gate):
    name="liquidity"
    def evaluate(self,p,f):
        ok=f.liquidity_score is not None and f.liquidity_score>=.55; return GateResult(self.name,ok,f"score={f.liquidity_score}",{"score":f.liquidity_score})

class MomentumGate(Gate):
    name="momentum"
    def evaluate(self,p,f):
        ok=f.short_momentum is not None and abs(f.short_momentum)<=.01; return GateResult(self.name,ok,f"momentum={f.short_momentum}",{"momentum":f.short_momentum})

class ExecutionQualityGate(Gate):
    name="execution_quality"
    def evaluate(self,p,f):
        ok=f.liquidity_score is not None and f.liquidity_score>.35; return GateResult(self.name,ok,"snapshot quote quality",{"score":f.liquidity_score})

class TimingGate(Gate):
    name="timing"
    def evaluate(self,p,f):
        local=f.ts.astimezone(f.ts.tzinfo); minutes=local.hour*60+local.minute; ok=570<=minutes<=885
        return GateResult(self.name,ok,f"minutes={minutes}",{"minutes":minutes})

class GateEngine:
    def __init__(self,gates:list[Gate]): self.gates=gates
    def evaluate(self,p,f): return [g.evaluate(p,f) for g in self.gates]

def default_gate_engine()->GateEngine:
    return GateEngine([MarketContextGate({"RANGE","VOLATILE"}),VolatilityGate(),LiquidityGate(),MomentumGate(),ExecutionQualityGate(),TimingGate()])
