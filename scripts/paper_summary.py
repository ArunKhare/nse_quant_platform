from __future__ import annotations

import argparse
from datetime import date

from nse_quant.persistence.duckdb_store import DuckDBStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily paper-trading summary")
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    store = DuckDBStore()
    summary = store.daily_paper_summary(args.date)

    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
