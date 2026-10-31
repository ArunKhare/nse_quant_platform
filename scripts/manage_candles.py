"""Canonical CLI for aggregation of persisted one-minute spot candles."""

from __future__ import annotations

import argparse
from datetime import date

from nse_quant.market_data.candle_aggregation import (
    INTERVALS,
    build_daily_candles,
    build_interval_candles,
)
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    daily = commands.add_parser("aggregate-daily")
    intraday = commands.add_parser("aggregate-intraday")
    for command in (daily, intraday):
        command.add_argument("--symbol", default="NIFTY")
    daily.add_argument("--start-date", type=date.fromisoformat, required=True)
    daily.add_argument("--end-date", type=date.fromisoformat, required=True)
    intraday.add_argument("--trade-date", type=date.fromisoformat, required=True)
    intraday.add_argument("--intervals", default="5m,15m,30m,60m")
    args = parser.parse_args(argv)
    if args.command == "aggregate-daily":
        if args.start_date > args.end_date:
            parser.error("--start-date must be <= --end-date")
    else:
        args.intervals = [item.strip() for item in args.intervals.split(",") if item.strip()]
        if not args.intervals:
            parser.error("--intervals must contain at least one supported interval")
        invalid = [item for item in args.intervals if item not in INTERVALS]
        if invalid:
            parser.error(f"Unsupported interval(s): {', '.join(invalid)}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = DuckDBStore()
    try:
        if args.command == "aggregate-daily":
            return build_daily_candles(
                store=store,
                symbol=args.symbol,
                start_date=args.start_date.isoformat(),
                end_date=args.end_date.isoformat(),
            )
        for interval in args.intervals:
            count = build_interval_candles(
                store=store,
                symbol=args.symbol,
                trade_date=args.trade_date.isoformat(),
                interval=interval,
            )
            print(
                f"{args.symbol}: built {count} {interval} candles "
                f"for {args.trade_date.isoformat()}",
            )
        return 0
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
