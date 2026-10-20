"""Check whether the research warehouse is ready for backtesting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_quant.research.backtest_readiness import (
    evaluate_backtest_readiness,
    write_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Parquet warehouse backtest readiness"
    )

    parser.add_argument(
        "--warehouse-glob",
        default=(
            "data/exports/underlying=NIFTY/"
            "year=*/month=*/option_stream_*.parquet"
        ),
    )
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--min-complete-days", type=int, default=20)
    parser.add_argument(
        "--min-iv-rv-aligned-days",
        type=int,
        default=10,
    )
    parser.add_argument("--min-regime-days", type=int, default=10)
    parser.add_argument(
        "--output",
        default="data/research/backtest_readiness.json",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    report = evaluate_backtest_readiness(
        warehouse_glob=args.warehouse_glob,
        underlying=args.underlying,
        min_complete_days=args.min_complete_days,
        min_iv_rv_aligned_days=args.min_iv_rv_aligned_days,
        min_regime_days=args.min_regime_days,
    )

    output_path = Path(args.output)
    write_report(report, output_path)

    print(json.dumps(report.__dict__, indent=2))
    print(f"Report written: {output_path}")

    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())