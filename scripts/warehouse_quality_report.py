"""Generate a data-quality report for partitioned option-stream data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.research.parquet_warehouse import (
    ParquetWarehouse,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--underlying",
        default="NIFTY",
    )

    parser.add_argument(
        "--start",
        required=True,
    )

    parser.add_argument(
        "--end",
        required=True,
    )

    parser.add_argument(
        "--warehouse-dir",
        default="data/exports",
    )

    parser.add_argument(
        "--output-dir",
        default="data/research/quality",
    )

    parser.add_argument(
        "--max-gap-minutes",
        type=float,
        default=5.0,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    warehouse = ParquetWarehouse(
        args.warehouse_dir
    )

    frame = warehouse.load_option_stream(
        underlying=args.underlying,
        start_date=args.start,
        end_date=args.end,
    )

    if frame.empty:
        print(
            "No warehouse data found for "
            "the requested range."
        )
        return 1

    frame["ts"] = pd.to_datetime(
        frame["ts"],
        utc=True,
    )

    frame["market_ts"] = frame[
        "ts"
    ].dt.tz_convert("Asia/Kolkata")

    frame["trade_date"] = frame[
        "market_ts"
    ].dt.date

    reports: list[dict[str, object]] = []

    for trade_date, day in frame.groupby(
        "trade_date"
    ):
        timestamps = (
            day["market_ts"]
            .drop_duplicates()
            .sort_values()
        )

        expiry_counts = day.groupby(
            "market_ts"
        )["expiry"].nunique()

        aligned_timestamps = expiry_counts[
            expiry_counts >= 2
        ]

        gaps = timestamps.diff().dt.total_seconds() / 60
        large_gaps = gaps[
            gaps > args.max_gap_minutes
        ]

        reports.append(
            {
                "trade_date": trade_date,
                "rows": len(day),
                "snapshots": len(timestamps),
                "first_snapshot": timestamps.min(),
                "last_snapshot": timestamps.max(),
                "aligned_snapshots": len(
                    aligned_timestamps
                ),
                "aligned_pct": round(
                    len(aligned_timestamps)
                    / len(timestamps)
                    * 100,
                    2,
                )
                if len(timestamps)
                else 0.0,
                "large_gaps": len(
                    large_gaps
                ),
                "largest_gap_minutes": round(
                    float(gaps.max())
                    if not gaps.empty
                    else 0.0,
                    2,
                ),
                "missing_ltp": int(
                    day["ltp"].isna().sum()
                ),
                "missing_delta": int(
                    day["delta"].isna().sum()
                ),
                "zero_or_negative_ltp": int(
                    (day["ltp"] <= 0)
                    .sum()
                ),
            }
        )

    report = pd.DataFrame(reports)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / (
            f"warehouse_quality_"
            f"{args.underlying}_"
            f"{args.start}_{args.end}.csv"
        )
    )

    report.to_csv(
        output_path,
        index=False,
    )

    print(report.to_string(index=False))
    print(f"Saved: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())