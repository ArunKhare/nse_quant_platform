"""Diagnose iron-condor trade construction for one day."""

from __future__ import annotations

import argparse

import pandas as pd

from nse_quant.research.iron_condor_backtest import (
    IronCondorBacktester,
    IronCondorConfig,
)
from nse_quant.research.parquet_warehouse import (
    ParquetWarehouse,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument(
        "--warehouse-dir",
        default="data/exports",
    )
    parser.add_argument("--short-delta", type=float, default=0.20)
    parser.add_argument("--wing-width", type=int, default=100)
    args = parser.parse_args()

    warehouse = ParquetWarehouse(args.warehouse_dir)

    frame = warehouse.load_option_stream(
        underlying=args.underlying,
        start_date=args.trade_date,
        end_date=args.trade_date,
    )

    if frame.empty:
        print("No warehouse rows for this date")
        return 1

    config = IronCondorConfig(
        underlying=args.underlying,
        short_delta=args.short_delta,
        wing_width=args.wing_width,
    )

    backtester = IronCondorBacktester(
        frame=frame,
        config=config,
    )

    day_frame = backtester.frame[
        backtester.frame["trade_date"]
        == pd.Timestamp(args.trade_date).date()
    ]

    per_ts = day_frame.groupby("ts")["expiry"].nunique()

    aligned_ts = per_ts[per_ts >= 2].index

    print(f"Rows: {len(day_frame)}")
    print(f"Snapshots: {day_frame['ts'].nunique()}")
    print(f"Aligned snapshots: {len(aligned_ts)}")

    if aligned_ts.empty:
        print("No snapshot contains both expiries")
        return 1

    entry_ts = aligned_ts.min()
    entry_snapshot = day_frame[
        day_frame["ts"] == entry_ts
    ]

    expiries = sorted(
        entry_snapshot["expiry"].unique()
    )

    print(f"Entry timestamp: {entry_ts}")
    print(f"Expiries: {expiries}")

    expiry = expiries[0]
    expiry_snapshot = entry_snapshot[
        entry_snapshot["expiry"] == expiry
    ]

    legs = backtester._select_legs(
        expiry_snapshot
    )

    if legs is None:
        print(
            "Could not select condor legs. "
            "Check delta coverage and wing availability."
        )

        puts = expiry_snapshot[
            expiry_snapshot["option_type"] == "PE"
        ]

        calls = expiry_snapshot[
            expiry_snapshot["option_type"] == "CE"
        ]

        print("Put rows:", len(puts))
        print("Call rows:", len(calls))
        print(
            "Put delta range:",
            puts["delta"].min(),
            puts["delta"].max(),
        )
        print(
            "Call delta range:",
            calls["delta"].min(),
            calls["delta"].max(),
        )
        return 1

    print("Selected legs:")

    for name, leg in legs.items():
        print(
            name,
            leg["option_type"],
            leg["strike"],
            leg["ltp"],
            leg["delta"],
        )

    credit = backtester._credit(legs)
    print(f"Entry credit: {credit}")

    exit_ts = aligned_ts.max()

    if exit_ts <= entry_ts:
        print("No later aligned snapshot for exit")
        return 1

    exit_snapshot = day_frame[
        day_frame["ts"] == exit_ts
    ]

    exit_legs = backtester._match_exit_legs(
        exit_snapshot=exit_snapshot,
        legs=legs,
    )

    if exit_legs is None:
        print(
            "Exit snapshot does not contain all four legs."
        )
        print(f"Exit timestamp: {exit_ts}")

        for name, leg in legs.items():
            matches = exit_snapshot[
                (
                    exit_snapshot["option_type"]
                    == leg["option_type"]
                )
                & (
                    exit_snapshot["strike"]
                    == leg["strike"]
                )
            ]

            print(
                name,
                leg["strike"],
                "matches:",
                len(matches),
            )

        return 1

    exit_credit = backtester._credit(exit_legs)

    print(f"Exit timestamp: {exit_ts}")
    print(f"Exit credit: {exit_credit}")
    print(
        "Simulated PnL:",
        (credit - exit_credit)
        * config.lot_size,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())