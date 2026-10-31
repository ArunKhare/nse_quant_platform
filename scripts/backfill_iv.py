"""Backfill underlying-level ATM IV history from option_stream.

uv run python scripts/backfill_iv.py --underlying NIFTY `
--from 2026-10-23T00:00:00+05:30 `
--to 2026-10-30T23:59:59+05:30
"""

from __future__ import annotations

import argparse
from datetime import datetime

from nse_quant.analytics.iv_history import derive_atm_iv_observations
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill ATM IV history from option_stream")

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--from",
        dest="from_dt",
        required=True,
        help="Start datetime in ISO format",
    )

    parser.add_argument(
        "--to",
        dest="to_dt",
        required=True,
        help="End datetime in ISO format",
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
            tradingsymbol,
            instrument_token,
            lot_size,
            ltp,
            bid,
            ask,
            volume,
            oi,
            iv,
            delta,
            gamma,
            vega,
            theta
        FROM option_stream
        WHERE underlying = ?
          AND ts >= ?
          AND ts <= ?
          AND iv IS NOT NULL
        ORDER BY ts
        """,
        [args.underlying, from_dt, to_dt],
    ).fetchall()

    observations = derive_atm_iv_observations(
        rows,
        underlying=args.underlying,
    )

    written = 0

    for ts, expiry, iv, spot in observations:
        written += store.write_underlying_iv_observation(
            ts=ts,
            underlying=args.underlying,
            expiry=expiry,
            iv=iv,
            spot=spot,
            source="atm_average_backfill",
        )

    count = store.count_underlying_iv_observations(underlying=args.underlying)

    print(f"Backfilled {written} IV observations for {args.underlying}; total={count}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
