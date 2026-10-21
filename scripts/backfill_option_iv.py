"""Backfill implied volatility into historical option_stream rows."""

from __future__ import annotations

import argparse
from datetime import datetime, time

from nse_quant.analytics.implied_volatility import (
    implied_volatility,
    time_to_expiry_years,
)
from nse_quant.core.constants import IST
from nse_quant.core.settings import get_settings
from nse_quant.persistence.duckdb_store import DuckDBStore

RISK_FREE_RATE = get_settings().analytics.risk_free_rate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill option IV from stored prices"
    )

    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--from", dest="from_dt", required=True)
    parser.add_argument("--to", dest="to_dt", required=True)
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=RISK_FREE_RATE,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from_dt = datetime.fromisoformat(args.from_dt)
    to_dt = datetime.fromisoformat(args.to_dt)

    if to_dt <= from_dt:
        raise SystemExit("--to must be later than --from")

    store = DuckDBStore()

    rows = store.conn.execute(
        """
        SELECT
            ts,
            spot,
            expiry,
            strike,
            option_type,
            ltp,
            instrument_token
        FROM option_stream
        WHERE underlying = ?
          AND ts >= ?
          AND ts <= ?
          AND ltp IS NOT NULL
          AND ltp > 0
          AND spot IS NOT NULL
        ORDER BY ts
        """,
        [args.underlying, from_dt, to_dt],
    ).fetchall()

    updated = 0
    skipped = 0

    for ts, spot, expiry, strike, option_type, ltp, token in rows:
        expiry_dt = datetime.combine(expiry, time(15, 30), tzinfo=IST)

        t = time_to_expiry_years(
            as_of=ts,
            expiry=expiry_dt,
        )

        iv = implied_volatility(
            option_price=ltp,
            spot=spot,
            strike=strike,
            time_to_expiry_years=t,
            risk_free_rate=args.risk_free_rate,
            option_type=option_type,
        )

        if iv is None:
            skipped += 1
            continue

        store.conn.execute(
            """
            UPDATE option_stream
            SET iv = ?
            WHERE ts = ?
              AND instrument_token = ?
            """,
            [iv, ts, token],
        )
        updated += 1

    print(
        f"IV backfill complete: updated={updated}, skipped={skipped}"
    )

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())