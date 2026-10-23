"""Build IV surface and term-structure research reports."""

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
