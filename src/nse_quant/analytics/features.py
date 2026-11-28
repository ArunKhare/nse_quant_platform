"""Feature calculations using centralized settings and canonical primitives."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import numpy as np
import pandas as pd

from nse_quant.analytics.option_analytics import enrich_quote
from nse_quant.core.calculations import (
    atm_iv as canonical_atm_iv,
)
from nse_quant.core.calculations import (
    classify_intraday_shape as canonical_intraday_shape,
)
from nse_quant.core.calculations import (
    iv_percentile as canonical_iv_percentile,
)
from nse_quant.core.calculations import (
    iv_rank as canonical_iv_rank,
)
from nse_quant.core.calculations import (
    realized_volatility as canonical_realized_volatility,
)
from nse_quant.core.models import (
    ChainSnapshot,
    IntradayShape,
    IVAnalytics,
    MarketFeatures,
    OptionType,
)
from nse_quant.core.settings import settings

FEATURE_HISTORY_REQUIREMENTS: dict[str, int] = {
    "realized_vol": 21,
    "sma20": 20,
    "sma50": 50,
    "atr14": 15,
    "momentum_5": 6,
}


def required_spot_history_closes() -> int:
    """Return the minimum number of completed closes needed by spot features."""
    return max(FEATURE_HISTORY_REQUIREMENTS.values())


def realized_volatility(
    returns: Iterable[float],
    window: int | None = None,
) -> float | None:
    """Compatibility wrapper; settings supply the default window."""
    return canonical_realized_volatility(
        closes=returns,
        window=window or settings.analytics.rv_window,
    )


def iv_rank(
    current: float,
    history: Iterable[float],
) -> float | None:
    """Compatibility wrapper around the canonical IV-rank primitive."""
    return canonical_iv_rank(
        current_iv=current,
        history=history,
    )


def iv_percentile(
    current: float,
    history: Iterable[float],
) -> float | None:
    """Compatibility wrapper around the canonical IV-percentile primitive."""
    return canonical_iv_percentile(
        current_iv=current,
        history=history,
    )


def classify_intraday_shape(
    spot: float,
    fast: float | None,
    slow: float | None,
    rv: float | None,
) -> IntradayShape:
    """Classify descriptive intraday spot structure; not an institutional regime."""
    return canonical_intraday_shape(
        spot=spot,
        fast_sma=fast,
        slow_sma=slow,
        realized_volatility=rv,
    )


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
    # ATM IV uses only quotes on the snapshot's own expiry: enrich_quote prices
    # every quote against snapshot.expiry, so other-expiry IVs are not comparable.
    atm_q = [q for q in enriched if q.instrument.strike == atm and q.instrument.expiry == snapshot.expiry]
    # Average the valid call/put IVs per strike. A dict keyed only by strike would
    # let the last quote (e.g. a put priced below intrinsic, iv=None) overwrite a
    # valid call IV, which is what made ATM IV None after 83e8a58.
    ivs_by_strike: dict[float, list[float]] = {}
    for q in atm_q:
        if q.iv is not None and np.isfinite(q.iv) and q.iv > 0:
            ivs_by_strike.setdefault(q.instrument.strike, []).append(float(q.iv))
    iv_by_strike: dict[float, float | None] = {
        strike: float(np.mean(values)) for strike, values in ivs_by_strike.items()
    }
    atm_iv = canonical_atm_iv(
        iv_by_strike=iv_by_strike,
        spot=snapshot.spot,
    )
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
    fast_window = settings.analytics.sma20_window
    slow_window = settings.analytics.sma50_window
    fast = float(close_series.tail(fast_window).mean()) if len(closes) >= fast_window else None
    slow = float(close_series.tail(slow_window).mean()) if len(closes) >= slow_window else None
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
        intraday_shape=classify_intraday_shape(snapshot.spot, fast, slow, rv),
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

    rank = canonical_iv_rank(current_iv=current_iv, history=values)

    return IVAnalytics(
        current_iv=current_iv,
        iv_min=lo,
        iv_max=hi,
        valid_history_count=int(values.size),
        iv_rank=rank,
        iv_percentile=canonical_iv_percentile(current_iv=current_iv, history=values),
    )
