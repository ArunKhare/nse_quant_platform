"""Compatibility entry point; prefer export_warehouse.py market-regimes."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.warehouse_exports import (
    build_regime_export_path as build_regime_export_path,
)
from nse_quant.persistence.warehouse_exports import (
    export_market_regimes,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--export-dir", type=Path, default=Path("data/exports"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = DuckDBStore()
    try:
        return export_market_regimes(
            store=store,
            export_dir=args.export_dir,
            underlying=args.symbol,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
        )
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
