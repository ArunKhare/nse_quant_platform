"""Compatibility entry point; prefer export_warehouse.py option-stream."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.warehouse_exports import (
    build_option_stream_export_path as build_option_stream_export_path,
)
from nse_quant.persistence.warehouse_exports import (
    export_option_stream,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default="NIFTY")
    parser.add_argument("--date", required=True)
    parser.add_argument("--export-dir", type=Path, default=Path("data/exports"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = DuckDBStore()
    try:
        return export_option_stream(
            store=store,
            export_dir=args.export_dir,
            underlying=args.underlying,
            trading_date=date.fromisoformat(args.date),
        )
    finally:
        store.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
