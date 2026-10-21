"""Validate Kite market-data connectivity for a short period."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from uuid import uuid4

# Make the repository root importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_quant.integrations.kite_auth import get_authenticated_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Kite market-data stream")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--config", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    kite = get_authenticated_kite()
    provider = KiteMarketDataProvider(kite)
    store = DuckDBStore()
    run_id = uuid4().hex
    end_time = time.monotonic() + args.seconds

    try:
        while time.monotonic() < end_time:
            snapshot = provider.get_chain_snapshot()
            rows = store.write_option_stream(run_id, snapshot)
            print(
                {
                    "underlying": snapshot.underlying,
                    "spot": snapshot.spot,
                    "quotes": len(snapshot.quotes),
                    "persisted_rows": rows,
                }
            )
            time.sleep(1)

    except KeyboardInterrupt:
        print("Stream check interrupted.")

    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())