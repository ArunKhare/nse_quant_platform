"""Build multi-expiry IV surface and term-structure research reports.

This script reads eligible option-stream observations from the legacy DuckDB
store, builds snapshot-level IV-surface metrics, aggregates them into daily
research summaries, and writes two CSV reports.

It is a research-only reporting tool. It does not acquire live market data,
modify ``option_stream``, build Medallion Bronze/Silver/Gold data, authorize
execution, or assert decision eligibility.

Data flow
---------

.. code-block:: text

    option_stream
      -> eligible IV/delta observations
      -> multi-expiry snapshot IV surface
      -> daily IV summary
      -> CSV research reports

Required inputs
---------------

For each option-stream row, the script requires:

- ``ts``
- ``underlying``
- ``expiry``
- ``strike``
- ``option_type``
- ``ltp``
- ``spot``
- ``iv``
- ``delta``

Rows are eligible only when:

- The underlying matches ``--underlying``.
- ``iv`` is non-null.
- ``delta`` is non-null.
- ``ltp`` is greater than zero.

Snapshot requirements
---------------------

A timestamp produces an IV-surface snapshot only when it contains at least two
distinct expiries and both the near and next expiry have an available ATM IV.

For each eligible near/next expiry pair, the script calculates:

- ``atm_iv_near``: Mean IV of the CE and PE contracts at the strike nearest
  to spot in the near expiry.
- ``atm_iv_next``: Mean IV of the CE and PE contracts at the strike nearest
  to spot in the next expiry.
- ``term_structure``: ``atm_iv_next - atm_iv_near``.
- ``put_call_skew``: IV of the out-of-the-money put nearest to spot minus IV
  of the out-of-the-money call nearest to spot.
- ``risk_reversal_25d``: IV of the call whose absolute delta is closest to
  0.25 minus IV of the put whose absolute delta is closest to 0.25.
- ``butterfly_25d``: ``2 * ATM call IV - 2 * 25-delta call IV``.

Daily summary
-------------

The daily report aggregates snapshot-level metrics by trading date using
medians:

- ``median_spot``
- ``median_atm_iv_near``
- ``median_atm_iv_next``
- ``median_term_structure``
- ``median_put_call_skew``
- ``median_risk_reversal``
- ``median_butterfly``
- ``snapshots``: Number of distinct IV-surface snapshot timestamps.

Output files
------------

The script writes:

.. code-block:: text

    <output-dir>/iv_surface_snapshots_<underlying>.csv
    <output-dir>/iv_surface_daily_<underlying>.csv

Command-line interface
----------------------

.. code-block:: powershell

    uv run python scripts/iv_surface_report.py `
      --underlying NIFTY `
      --from 2026-10-18 `
      --to 2026-11-19 `
      --output-dir data/research

Limitations
-----------

- A date with only one expiry cannot produce an IV-surface snapshot.
- A date with missing delta cannot produce risk-reversal or butterfly metrics.
- A date with missing IV or non-positive LTP is excluded from ATM IV and skew
  calculations.
- The script does not fill, interpolate, or synthesize missing IV, delta,
  prices, expiries, or contracts.
- It does not calculate daily IV rank, realized volatility, market regimes, or
  decision eligibility.

Examples
--------

Build reports for NIFTY:

.. code-block:: powershell

    uv run python scripts/iv_surface_report.py `
      --underlying NIFTY `
      --from 2026-10-18 `
      --to 2026-11-19

Write reports to the Milestone 2 research directory:

.. code-block:: powershell

    uv run python scripts/iv_surface_report.py `
      --underlying NIFTY `
      --from 2026-10-18 `
      --to 2026-11-19 `
      --output-dir data/research/milestone2
"""

from __future__ import annotations

import argparse

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.iv_surface import (
    build_daily_iv_summary,
    build_iv_surface_report,
    save_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build IV surface research reports")

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        help="Start date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--to",
        dest="to_date",
        required=True,
        help="End date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--output-dir",
        default="data/research",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    store = DuckDBStore(read_only=True)

    try:
        frame = store.conn.execute(
            """
            SELECT
                ts,
                underlying,
                expiry,
                strike,
                option_type,
                ltp,
                spot,
                iv,
                delta
            FROM option_stream
            WHERE underlying = ?
              AND CAST(ts AS DATE) BETWEEN ? AND ?
              AND iv IS NOT NULL
              AND delta IS NOT NULL
            ORDER BY ts
            """,
            [args.underlying, args.from_date, args.to_date],
        ).fetchdf()

        if frame.empty:
            print("No eligible option-stream rows found for the requested date range.")
            return 1

        snapshot_report = build_iv_surface_report(
            frame,
            underlying=args.underlying,
        )

        if snapshot_report.empty:
            print("Not enough multi-expiry snapshots to build an IV surface report.")
            return 1

        daily_report = build_daily_iv_summary(snapshot_report)

        snapshot_path, daily_path = save_reports(
            snapshot_report=snapshot_report,
            daily_report=daily_report,
            output_dir=args.output_dir,
            underlying=args.underlying,
        )

        print(
            {
                "snapshots": len(snapshot_report),
                "days": len(daily_report),
                "snapshot_report": str(snapshot_path),
                "daily_report": str(daily_path),
            }
        )

        return 0

    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
