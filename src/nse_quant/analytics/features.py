"""Feature calculations using centralized settings."""
from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from .option_analytics import enrich_quote
except ImportError:  # pragma: no cover
    from analytics.option_analytics import enrich_quote
from ..core.constants import TRADING_DAYS_PER_YEAR
from ..core.models import ChainSnapshot, MarketFeatures, MarketRegime, OptionType
from ..core.settings import settings


def realized_volatility(returns:Iterable[float],window:int|None=None)->float|None:
    window=window or settings.analytics.rv_window; s=pd.Series(list(returns),dtype=float).dropna()
    if len(s)<window+1: return None
    return float(s.tail(window+1).pct_change().dropna().std(ddof=1)*math.sqrt(TRADING_DAYS_PER_YEAR))

def iv_rank(current:float,history:Iterable[float])->float|None:
    v=np.asarray(list(history),float); v=v[np.isfinite(v)&(v>0)]
    if not v.size: return None
    lo,hi=float(v.min()),float(v.max()); return 50.0 if hi<=lo else float((current-lo)/(hi-lo)*100)

def iv_percentile(current:float,history:Iterable[float])->float|None:
    v=np.asarray(list(history),float); v=v[np.isfinite(v)&(v>0)]
    return float((v<current).mean()*100) if v.size else None

def positioning(snapshot:ChainSnapshot):
    call_oi=sum(q.oi or 0 for q in snapshot.quotes if q.instrument.option_type==OptionType.CE)
    put_oi=sum(q.oi or 0 for q in snapshot.quotes if q.instrument.option_type==OptionType.PE)
    pcr=put_oi/call_oi if call_oi else None; pain=[]
    for k in sorted({q.instrument.strike for q in snapshot.quotes}):
        loss=sum((max(0,k-q.instrument.strike) if q.instrument.option_type==OptionType.CE else max(0,q.instrument.strike-k))*(q.oi or 0) for q in snapshot.quotes); pain.append((loss,k))
    return call_oi,put_oi,pcr,(min(pain)[1] if pain else None)

def liquidity_score(snapshot:ChainSnapshot)->float:
    scores=[]
    for q in snapshot.quotes:
        spread=q.spread_pct
        scores.append(.45*(1 if spread is None else max(0,1-spread/.05))+.35*min((q.oi or 0)/100000,1)+.2*min((q.volume or 0)/5000,1))
    return float(np.mean(scores)) if scores else 0

def classify_regime(spot:float,fast:float,slow:float,rv:float|None)->MarketRegime:
    if rv is not None and rv > 0.35:
        return MarketRegime.VOLATILE

    if fast is None or slow is None:
        return MarketRegime.UNKNOWN
    if fast > slow * 1.002:
        return MarketRegime.TREND_UP
    if fast < slow * .998:
        return MarketRegime.TREND_DOWN
    return MarketRegime.RANGE

def build_features(snapshot:ChainSnapshot,iv_history:Iterable[float]=(),close_history:Iterable[float]=(),now:datetime|None=None)->MarketFeatures:
    now = now or snapshot.ts
    rate = settings.analytics.risk_free_rate
    enriched = [enrich_quote(q,snapshot.spot,snapshot.expiry,now,rate) for q in snapshot.quotes]
    atm = snapshot.atm_strike()
    atm_q = [q for q in enriched if q.instrument.strike==atm]
    ivs = [q.iv for q in atm_q if q.iv is not None]
    atm_iv = float(np.mean(ivs)) if ivs else None
    call_oi,put_oi,pcr,max_pain = positioning(snapshot)
    rv=realized_volatility(close_history)
    if rv is not None and rv <= 0:
        rv = None
    spread = atm_iv-rv if atm_iv is not None and rv is not None else None

    calls = {q.instrument.strike:q for q in enriched if q.instrument.option_type==OptionType.CE}
    puts = {q.instrument.strike:q for q in enriched if q.instrument.option_type==OptionType.PE}
    straddle = None
    if atm in calls and atm in puts:
        c=calls[atm].mid or calls[atm].ltp; p=puts[atm].mid or puts[atm].ltp; straddle=c+p if c and p else None
    emp = straddle*.85 if straddle else None
    closes = list(close_history)
    fast=float(pd.Series(closes).tail(20).mean()) if len(closes)>=20 else None
    slow = float(pd.Series(closes).tail(50).mean()) if len(closes)>=50 else None
    momentum = (closes[-1]/closes[-6]-1) if len(closes)>=6 else None

    return MarketFeatures(
        ts=now,
        underlying=snapshot.underlying,
        spot=snapshot.spot,
        expiry=snapshot.expiry,
        atm_iv=atm_iv,
        iv_rank=iv_rank(atm_iv,iv_history) if atm_iv is not None else None,
        iv_percentile=iv_percentile(atm_iv,iv_history) if atm_iv is not None else None,
        realized_vol=rv,
        iv_rv_spread=spread,
        pcr=pcr,
        total_call_oi=call_oi,
        total_put_oi=put_oi,
        max_pain=max_pain,
        liquidity_score=liquidity_score(snapshot),
        regime=classify_regime(snapshot.spot,fast,slow,rv),
        short_momentum=momentum,
        straddle_price=straddle,
        expected_move_pct=emp/snapshot.spot*100 if emp else None,expected_move_points=emp)
