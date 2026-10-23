"""Derive underlying-level IV history from normalized option snapshots."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

AtmIVObservation = tuple[datetime, date, float, float | None]


def derive_atm_iv_observations(
    rows: list[tuple[Any, ...]],
    *,
    underlying: str,
) -> list[AtmIVObservation]:
    """Derive one ATM-average IV observation per chain snapshot.

    Expected `rows` shape matches the replay exporter query:
    ts, spot, expiry, strike, option_type, tradingsymbol,
    instrument_token, lot_size, ltp, bid, ask, volume, oi,
    iv, delta, gamma, vega, theta
    """
    by_snapshot: dict[
        tuple[datetime, float, date],
        list[tuple[float, float]],
    ] = defaultdict(list)

    for row in rows:
        (
            ts,
            spot,
            expiry,
            strike,
            _option_type,
            _tradingsymbol,
            _instrument_token,
            _lot_size,
            _ltp,
            _bid,
            _ask,
            _volume,
            _oi,
            iv,
            _delta,
            _gamma,
            _vega,
            _theta,
        ) = row

        if spot is None or iv is None or iv <= 0:
            continue

        by_snapshot[(ts, spot, expiry)].append((strike, iv))

    observations: list[AtmIVObservation] = []

    for (ts, spot, expiry), quote_ivs in sorted(
        by_snapshot.items(),
        key=lambda item: item[0][0],
    ):
        if not quote_ivs:
            continue

        atm_strike = min(
            quote_ivs,
            key=lambda item: abs(item[0] - spot),
        )[0]

        atm_ivs = [iv for strike, iv in quote_ivs if strike == atm_strike]

        if not atm_ivs:
            continue

        observations.append(
            (
                ts,
                expiry,
                sum(atm_ivs) / len(atm_ivs),
                spot,
            )
        )

    return observations
