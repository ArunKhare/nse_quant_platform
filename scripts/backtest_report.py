"""Generate a QuantStats report from iron-condor daily returns."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import quantstats as qs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--returns", required=True)
    parser.add_argument(
        "--output",
        default=(
            "data/research/milestone2/"
            "quantstats_report.html"
        ),
    )
    args = parser.parse_args()

    frame = pd.read_csv(
        args.returns,
        parse_dates=["trade_date"],
    )

    returns = frame.set_index("trade_date")[
        "daily_return"
    ]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    qs.reports.html(
        returns,
        output=str(output),
        title="NIFTY Iron Condor Backtest",
    )

    print(f"QuantStats report saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())