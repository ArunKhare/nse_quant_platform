"""Backfill missing Black-Scholes Greeks into persisted option streams.

Recomputes Black-Scholes Greeks only for historical option rows that already
have a valid IV and spot, and only where one or more Greeks are missing.

Calculates:

- delta
- gamma
- vega
- theta

Updates:

- option_stream.delta
- option_stream.gamma
- option_stream.vega
- option_stream.theta

Safety
------

This script never overwrites an existing non-null Greek. It uses COALESCE so
that only missing values are filled.

Run order
---------

.. code-block:: text

    backfill_option_iv.py
      -> backfill_option_greeks.py
      -> backfill_iv.py

Examples
--------

Backfill one trading date:

.. code-block:: powershell

    uv run python scripts/backfill_option_greeks.py `
      --underlying NIFTY `
      --trade-date 2026-11-19 `
      --risk-free-rate 0.065

Backfill a date range:

.. code-block:: powershell

    uv run python scripts/backfill_option_greeks.py `
      --underlying NIFTY `
      --from 2026-10-18T00:00:00+05:30 `
      --to 2026-11-19T23:59:59+05:30 `
      --risk-free-rate 0.065
"""

from __future__ import annotations

import argparse
import math
import time
from datetime import datetime
from datetime import time as dt_time

from nse_quant.analytics.implied_volatility import time_to_expiry_years
from nse_quant.analytics.option_analytics import bs_price_greeks
from nse_quant.core.constants import IST
from nse_quant.persistence.duckdb_store import DuckDBStore

CHUNK_SIZE = 5_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing Black-Scholes Greeks.",
    )
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument(
        "--trade-date",
        type=lambda value: datetime.fromisoformat(value),
        default=None,
    )
    parser.add_argument(
        "--from",
        dest="from_dt",
        type=lambda value: datetime.fromisoformat(value),
        default=None,
    )
    parser.add_argument(
        "--to",
        dest="to_dt",
        type=lambda value: datetime.fromisoformat(value),
        default=None,
    )
    parser.add_argument("--risk-free-rate", type=float, default=0.065)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    return parser.parse_args()


def resolve_range(
    args: argparse.Namespace,
) -> tuple[datetime, datetime]:
    if args.trade_date is not None:
        start = datetime.combine(
            args.trade_date.date(),
            dt_time.min,
            tzinfo=IST,
        )
        end = datetime.combine(
            args.trade_date.date(),
            dt_time(23, 59, 59),
            tzinfo=IST,
        )
        return start, end

    if args.from_dt is None or args.to_dt is None:
        raise SystemExit("Provide either --trade-date or both --from and --to.")

    if args.to_dt < args.from_dt:
        raise SystemExit("--to must be after --from")

    return args.from_dt, args.to_dt


def main() -> int:
    args = parse_args()
    start_dt, end_dt = resolve_range(args)

    store = DuckDBStore()

    try:
        total = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM option_stream
            WHERE underlying = ?
              AND ts >= ?
              AND ts <= ?
              AND iv IS NOT NULL
              AND iv > 0
              AND spot IS NOT NULL
              AND (
                  delta IS NULL
                  OR gamma IS NULL
                  OR vega IS NULL
                  OR theta IS NULL
              )
            """,
            [args.underlying, start_dt, end_dt],
        ).fetchone()[0]

        print(
            f"Rows requiring Greeks backfill: {total:,}",
            flush=True,
        )

        if total == 0:
            return 0

        query = """
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
              AND ts >= ?
              AND ts <= ?
              AND iv IS NOT NULL
              AND iv > 0
              AND spot IS NOT NULL
              AND (
                  delta IS NULL
                  OR gamma IS NULL
                  OR vega IS NULL
                  OR theta IS NULL
              )
            ORDER BY ts, instrument_token
        """

        rows = store.conn.execute(
            query,
            [args.underlying, start_dt, end_dt],
        ).fetchall()

        print(
            f"Fetched {len(rows):,} candidate rows",
            flush=True,
        )

        updated = 0
        processed = 0
        skipped = 0
        time.monotonic()

        for chunk_start in range(0, len(rows), args.chunk_size):
            chunk = rows[chunk_start : chunk_start + args.chunk_size]
            updates: list[tuple[float, float, float, float, datetime, int]] = []

            for ts, spot, expiry, strike, option_type, iv, token in chunk:
                expiry_dt = datetime.combine(
                    expiry,
                    dt_time(15, 30),
                    tzinfo=IST,
                )

                ttm = time_to_expiry_years(
                    as_of=ts,
                    expiry=expiry_dt,
                )

                if not math.isfinite(ttm) or ttm <= 0:
                    skipped += 1
                    continue

                try:
                    _, delta, gamma, vega, theta = bs_price_greeks(
                        spot=spot,
                        strike=strike,
                        ttm=ttm,
                        rate=args.risk_free_rate,
                        iv=iv,
                        option_type=option_type,
                    )
                except (ValueError, ZeroDivisionError, OverflowError):
                    skipped += 1
                    continue

                updates.append(
                    (
                        delta,
                        gamma,
                        vega,
                        theta,
                        ts,
                        token,
                    )
                )

            if updates:
                store.conn.executemany(
                    """
                    UPDATE option_stream
                    SET
                        delta = COALESCE(delta, ?),
                        gamma = COALESCE(gamma, ?),
                        vega = COALESCE(vega, ?),
                        theta = COALESCE(theta, ?)
                    WHERE ts = ?
                    AND instrument_token = ?
                    """,
                    updates,
                )
                updated += len(updates)

            processed += len(rows)

            print(
                f"Processed {processed:,}/{total:,} | updated {updated:,} | skipped {skipped:,}",
                flush=True,
            )

        print(
            f"Completed: updated {updated:,} rows, skipped {skipped:,} invalid rows",
            flush=True,
        )

    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
