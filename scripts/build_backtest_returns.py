"""Build daily returns from an iron-condor trades CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--trades-csv",
        required=True,
    )

    parser.add_argument(
        "--output",
        default=None,
    )

    parser.add_argument(
        "--capital",
        type=float,
        default=100000.0,
        help="Capital base used to convert PnL to returns",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    trades_path = Path(args.trades_csv)

    if not trades_path.exists():
        print(f"Trades file not found: {trades_path}")
        return 1

    trades = pd.read_csv(trades_path)

    required = {
        "exit_ts",
        "pnl",
    }

    missing = required.difference(trades.columns)

    if missing:
        print(f"Missing required columns: {sorted(missing)}")
        return 1

    if trades.empty:
        print("No trades found.")
        return 1

    trades["exit_ts"] = pd.to_datetime(
        trades["exit_ts"],
        utc=True,
    )

    trades["trade_date"] = trades["exit_ts"].dt.tz_convert("Asia/Kolkata").dt.date

    daily_pnl = trades.groupby("trade_date")["pnl"].sum().sort_index()

    all_days = pd.date_range(
        start=min(daily_pnl.index),
        end=max(daily_pnl.index),
        freq="D",
    ).date

    daily_pnl = daily_pnl.reindex(
        all_days,
        fill_value=0.0,
    )

    returns_frame = pd.DataFrame(
        {
            "trade_date": daily_pnl.index,
            "daily_pnl": daily_pnl.values,
            "daily_return": (daily_pnl.values / args.capital),
        }
    )

    output_path = (
        Path(args.output)
        if args.output
        else trades_path.with_name(f"{trades_path.stem}_daily_returns.csv")
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    returns_frame.to_csv(
        output_path,
        index=False,
    )

    print(
        {
            "days": len(returns_frame),
            "trading_days": int((returns_frame["daily_pnl"] != 0).sum()),
            "total_pnl": round(
                float(returns_frame["daily_pnl"].sum()),
                2,
            ),
            "returns_file": str(output_path),
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
