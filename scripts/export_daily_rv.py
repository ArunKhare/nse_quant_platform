"""Export daily realized-volatility observations to a research CSV.

Reads daily_rv_observations from the legacy DuckDB store and writes a
sorted CSV for downstream Milestone 2 RV-regime research.

Example:
uv run python scripts/export_daily_rv.py --symbol NIFTY
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export daily RV observations to a research CSV.",
    )
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--output",
        default="data/research/daily_rv_NIFTY.csv",
    )
    args = parser.parse_args()

    store = DuckDBStore(read_only=True)

    try:
        frame = store.conn.execute(
            """
            SELECT
                symbol AS underlying,
                CAST(trading_date AS DATE) AS trade_date,
                rv AS realized_volatility,
                observation_count
            FROM daily_rv_observations
            WHERE symbol = ?
            ORDER BY trade_date
            """,
            [args.symbol],
        ).fetchdf()
    finally:
        store.close()

    if frame.empty:
        raise SystemExit(f"No daily RV observations found for {args.symbol}")

    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)

    print(
        f"Exported {len(frame)} daily RV observations for {args.symbol}: "
        f"{frame['trade_date'].min()} to {frame['trade_date'].max()}"
    )
    print(f"Saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
