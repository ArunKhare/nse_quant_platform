"""Backfill Black-Scholes Greeks into persisted option streams."""

from __future__ import annotations

import argparse
from datetime import datetime, time

from nse_quant.analytics.implied_volatility import (
    time_to_expiry_years,
)
from nse_quant.analytics.option_analytics import (
    bs_price_greeks,
)
from nse_quant.core.constants import IST
from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--risk-free-rate", type=float, default=0.065)
    args = parser.parse_args()

    store = DuckDBStore()

    rows = store.conn.execute(
        """
        SELECT
            ts,
            spot,
            expiry,
            strike,
            option_type,
            iv,
            instrument_token
        FROM option_stream
        WHERE underlying = ?
          AND CAST(ts AS DATE) = ?
          AND iv IS NOT NULL
          AND iv > 0
          AND spot IS NOT NULL
        """,
        [args.underlying, args.trade_date],
    ).fetchall()

    updated = 0

    for ts, spot, expiry, strike, option_type, iv, token in rows:
        expiry_dt = datetime.combine(
            expiry,
            time(15, 30),
            tzinfo=IST,
        )

        ttm = time_to_expiry_years(
            as_of=ts,
            expiry=expiry_dt,
        )

        try:
            _, delta, gamma, vega, theta = bs_price_greeks(
                spot=spot,
                strike=strike,
                ttm=ttm,
                rate=args.risk_free_rate,
                iv=iv,
                option_type=option_type,
            )
        except ValueError:
            continue

        store.conn.execute(
            """
            UPDATE option_stream
            SET delta = ?,
                gamma = ?,
                vega = ?,
                theta = ?
            WHERE ts = ?
              AND instrument_token = ?
            """,
            [delta, gamma, vega, theta, ts, token],
        )

        updated += 1

    print(f"Backfilled Greeks for {updated} rows")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
