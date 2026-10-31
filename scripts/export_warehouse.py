"""Export persisted data into the partitioned Parquet warehouse."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.warehouse_exports import (
    export_market_regimes,
    export_option_stream,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    option = commands.add_parser("option-stream")
    regimes = commands.add_parser("market-regimes")
    for command in (option, regimes):
        command.add_argument("--underlying", "--symbol", dest="underlying", default="NIFTY")
        command.add_argument("--export-dir", type=Path, default=Path("data/exports"))
    option.add_argument("--date", type=date.fromisoformat, required=True)
    regimes.add_argument("--start-date", type=date.fromisoformat, required=True)
    regimes.add_argument("--end-date", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    if args.command == "market-regimes" and args.start_date > args.end_date:
        parser.error("--start-date must be <= --end-date")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = DuckDBStore()
    try:
        if args.command == "option-stream":
            return export_option_stream(
                store=store,
                export_dir=args.export_dir,
                underlying=args.underlying,
                trading_date=args.date,
            )
        return export_market_regimes(
            store=store,
            export_dir=args.export_dir,
            underlying=args.underlying,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
