"""Export persisted Legacy db data into the partitioned Parquet warehouse.
Command         Source table   Output
option-stream  option_stream  One Parquet file for the selected underlying and date.
market-regimes market_regimes One Parquet file for each available regime day in the range.
source: data/nse_quant.duckdb
output: data/exports

Option-stream export
-------------------
- after a trading day’s option_stream rows are complete:

uv run python scripts/export_warehouse.py option-stream `
  --underlying NIFTY `
  --date 2026-11-19

Market-regime export
--------------------
Use this after build_daily_market_regimes.py has written regimes:
uv run python scripts/export_warehouse.py market-regimes `
  --underlying NIFTY `
  --start-date 2026-10-18 `
  --end-date 2026-11-19

Important limitations
- It exports one option-stream day at a time; there is no bulk date-range option-stream command.
- It does not export spot_candles, spot_features, daily_rv_observations, or underlying_iv_observations.
- It does not validate IV coverage or snapshot count; that validation is performed by
    Legacy_run_warehouse_validate_research.py after export.

uses the legacy DuckDB store, not Medallion Bronze/Silver/Gold.

Option-Stream export contains trading day's rows per symbol:
[run_id,ts,underlying,expiry,strike,option_type,tradingsymbol,instrument_token,lot_size,spot,ltp,
bid,ask,volume,oi,iv,delta,gamma,vega,theta,quote_status,payload_json]

The regime export contains the latest regime row per symbol for each date:
[ts, trend_regime, volatility_regime, iv_regime, regime, features]
"""

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
