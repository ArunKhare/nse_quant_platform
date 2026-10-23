"""Build single-expiry IV research from a validated Parquet file."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.research.iv_surface import (
    build_single_expiry_iv_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--output",
        default=("data/research/milestone2/single_expiry_iv_snapshots_NIFTY.csv"),
    )
    args = parser.parse_args()

    frame = pd.read_parquet(args.parquet)

    report = build_single_expiry_iv_report(
        frame,
        underlying=args.symbol,
    )

    if report.empty:
        raise SystemExit("No valid IV observations found")

    daily = report.groupby("trade_date", as_index=False).agg(
        underlying=("underlying", "first"),
        expiry=("expiry", "first"),
        median_spot=("spot", "median"),
        median_atm_iv=("atm_iv", "median"),
        mean_atm_iv=("atm_iv", "mean"),
        min_atm_iv=("atm_iv", "min"),
        max_atm_iv=("atm_iv", "max"),
        median_put_call_skew=("put_call_skew", "median"),
        median_risk_reversal=("risk_reversal_25d", "median"),
        median_butterfly=("butterfly_25d", "median"),
        snapshots=("ts", "nunique"),
    )

    output = Path(args.output)

    daily_path = output.with_name(output.name.replace("snapshots", "daily"))

    daily_path.parent.mkdir(parents=True, exist_ok=True)

    daily.to_csv(daily_path, index=False)

    print(f"Built {len(daily)} single-expiry IV snapshots for {args.symbol}")
    print(f"Saved daily summary: {daily_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
