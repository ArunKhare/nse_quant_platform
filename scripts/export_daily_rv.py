"""Export daily realized-volatility observations to CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument(
        "--output",
        default="data/research/daily_rv_NIFTY.csv",
    )
    args = parser.parse_args()

    store = DuckDBStore(read_only=True)

    frame = store.conn.execute(
        """
        SELECT
            trading_date,
            symbol,
            rv AS realized_volatility,
            observation_count
        FROM daily_rv_observations
        WHERE symbol = ?
        ORDER BY trading_date
        """,
        [args.symbol],
    ).fetchdf()

    store.close()

    if frame.empty:
        raise SystemExit(
            f"No daily RV observations found for {args.symbol}"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    frame.to_csv(output, index=False)

    print(
        f"Exported {len(frame)} daily RV observations "
        f"to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())