"""Feature calculations using centralized settings."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime

import numpy as np
import pandas as pd

from ..core.constants import TRADING_DAYS_PER_YEAR
from ..core.models import ChainSnapshot, IVAnalytics, MarketFeatures, MarketRegime, OptionType
from ..core.settings import settings
from .option_analytics import enrich_quote


def realized_volatility(returns: Iterable[float], window: int | None = None) -> float | None:
    window = window or settings.analytics.rv_window
    s = pd.Series(list(returns), dtype=float).dropna()
    if len(s) < window + 1:
        return None
    return float(
        s.tail(window + 1).pct_change().dropna().std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
    )


def iv_rank(current: float, history: Iterable[float]) -> float | None:
    """Return IV rank in the inclusive range 0-100, or None if unavailable."""
    if not np.isfinite(current) or current <= 0:
        return None

    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values) & (values > 0)]

    if values.size == 0:
        return None

    lo = float(values.min())
    hi = float(values.max())

    if hi <= lo:
        return 50.0

    raw_rank = ((current - lo) / (hi - lo)) * 100.0
    return float(max(0.0, min(100.0, raw_rank)))


def iv_percentile(current: float, history: Iterable[float]) -> float | None:
    v = np.asarray(list(history), float)
    v = v[np.isfinite(v) & (v > 0)]
    return float((v < current).mean() * 100) if v.size else None


def positioning(snapshot: ChainSnapshot):
    call_oi = sum(q.oi or 0 for q in snapshot.quotes if q.instrument.option_type == OptionType.CE)
    put_oi = sum(q.oi or 0 for q in snapshot.quotes if q.instrument.option_type == OptionType.PE)
    pcr = put_oi / call_oi if call_oi else None
    pain = []
    for k in sorted({q.instrument.strike for q in snapshot.quotes}):
        loss = sum(
            (
                max(0, k - q.instrument.strike)
                if q.instrument.option_type == OptionType.CE
                else max(0, q.instrument.strike - k)
            )
            * (q.oi or 0)
            for q in snapshot.quotes
        )
        pain.append((loss, k))
    return call_oi, put_oi, pcr, (min(pain)[1] if pain else None)


def liquidity_score(snapshot: ChainSnapshot) -> float:
    scores = []
    for q in snapshot.quotes:
        spread = q.spread_pct
        scores.append(
            0.45 * (1 if spread is None else max(0, 1 - spread / 0.05))
            + 0.35 * min((q.oi or 0) / 100000, 1)
            + 0.2 * min((q.volume or 0) / 5000, 1)
        )
    return float(np.mean(scores)) if scores else 0


def classify_regime(
    spot: float,
    fast: float | None,
    slow: float | None,
    rv: float | None,
) -> MarketRegime:
    if rv is not None and rv > 0.35:
        return MarketRegime.VOLATILE

    if fast is None or slow is None:
        return MarketRegime.UNKNOWN
    if fast > slow * 1.002:
        return MarketRegime.TREND_UP
    if fast < slow * 0.998:
        return MarketRegime.TREND_DOWN
    return MarketRegime.RANGE


def build_features(
    snapshot: ChainSnapshot,
    iv_history: Iterable[float] = (),
    close_history: Iterable[float] = (),
    now: datetime | None = None,
) -> MarketFeatures:
    now = now or snapshot.ts
    rate = settings.analytics.risk_free_rate
    enriched = [enrich_quote(q, snapshot.spot, snapshot.expiry, now, rate) for q in snapshot.quotes]
    atm = snapshot.atm_strike()
    atm_q = [q for q in enriched if q.instrument.strike == atm]
    ivs = [q.iv for q in atm_q if q.iv is not None]
    atm_iv = float(np.mean(ivs)) if ivs else None
    call_oi, put_oi, pcr, max_pain = positioning(snapshot)
    rv = realized_volatility(close_history)
    if rv is not None and rv <= 0:
        rv = None
    spread = atm_iv - rv if atm_iv is not None and rv is not None else None

    calls = {q.instrument.strike: q for q in enriched if q.instrument.option_type == OptionType.CE}
    puts = {q.instrument.strike: q for q in enriched if q.instrument.option_type == OptionType.PE}
    straddle = None
    if atm in calls and atm in puts:
        c = calls[atm].mid or calls[atm].ltp
        p = puts[atm].mid or puts[atm].ltp
        straddle = c + p if c and p else None
    emp = straddle * 0.85 if straddle else None
    closes = list(close_history)
    close_series = pd.Series(closes, dtype=float)
    fast = float(close_series.tail(20).mean()) if len(closes) >= 20 else None
    slow = float(close_series.tail(50).mean()) if len(closes) >= 50 else None
    momentum = (closes[-1] / closes[-6] - 1) if len(closes) >= 6 and closes[-6] > 0 else None

    iv_analytics = build_iv_analytics(atm_iv, iv_history)

    return MarketFeatures(
        ts=now,
        underlying=snapshot.underlying,
        spot=snapshot.spot,
        expiry=snapshot.expiry,
        atm_iv=atm_iv,
        realized_vol=rv,
        iv_rv_spread=spread,
        iv_rank=iv_analytics.iv_rank,
        iv_percentile=iv_analytics.iv_percentile,
        iv_analytics=iv_analytics,
        pcr=pcr,
        total_call_oi=call_oi,
        total_put_oi=put_oi,
        max_pain=max_pain,
        liquidity_score=liquidity_score(snapshot),
        regime=classify_regime(snapshot.spot, fast, slow, rv),
        short_momentum=momentum,
        straddle_price=straddle,
        expected_move_pct=(emp / snapshot.spot * 100 if emp and snapshot.spot > 0 else None),
        expected_move_points=emp,
    )


def build_iv_analytics(
    current_iv: float | None,
    history: Iterable[float],
) -> IVAnalytics:
    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values) & (values > 0)]

    if current_iv is None or not np.isfinite(current_iv) or current_iv <= 0 or values.size == 0:
        return IVAnalytics(valid_history_count=int(values.size))

    lo = float(values.min())
    hi = float(values.max())

    rank = 50.0 if hi <= lo else max(0.0, min(100.0, (current_iv - lo) / (hi - lo) * 100.0))

    return IVAnalytics(
        current_iv=current_iv,
        iv_min=lo,
        iv_max=hi,
        valid_history_count=int(values.size),
        iv_rank=rank,
        iv_percentile=iv_percentile(current_iv, values),
    )
