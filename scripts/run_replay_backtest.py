"""Run DecisionLoop over exported chain-snapshot replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.market_data.replay_provider import (
    ReplayExhaustedError,
    ReplayMarketDataProvider,
)
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.strategy.decision_loop import DecisionLoop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate closed trades from replay snapshots"
    )

    parser.add_argument(
        "--replay-file",
        required=True,
        help="Replay JSON file containing chain snapshots",
    )

    parser.add_argument(
        "--database",
        required=True,
        help="DuckDB database file for this replay run",
    )

    parser.add_argument(
        "--symbol",
        default=None,
        help="Underlying symbol; defaults to configured default",
    )

    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional maximum number of replay cycles",
    )

    return parser.parse_args()


def load_replay_snapshots(
    replay_file: Path,
) -> list[Any]:
    payload = json.loads(replay_file.read_text(encoding="utf-8"))

    snapshots = payload.get("snapshots")

    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError(
            f"No replay snapshots found in {replay_file}"
        )

    return snapshots


def main() -> int:
    args = parse_args()
    settings = get_settings()

    replay_file = Path(args.replay_file)
    database_path = Path(args.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    snapshots = load_replay_snapshots(replay_file)

    provider = ReplayMarketDataProvider(snapshots)
    store = DuckDBStore(database_path)
    broker = PaperBroker()

   
    loop = DecisionLoop(
        store=store,
        provider=provider,
        broker=broker,
        run_id=f"replay:{replay_file.stem}",
        settings=settings,
        spot_instrument_token_resolver=lambda _symbol: 256265,
        live_snapshot_path=database_path.with_suffix(
            ".live_snapshot.json"
        ),
    )

    cycle_count = 0
    status_counts: dict[str, int] = {}

    try:
        for _ in snapshots:
            if (
                args.max_cycles is not None
                and cycle_count >= args.max_cycles
            ):
                break

            try:
                result = loop.run_once()

            except ReplayExhaustedError:
                print("Replay exhausted.")
                break
            except Exception as exc:  # noqa:BLE001
                result = {
                    "status": "loop_error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

            status = result.get("status", "unknown")
            status_counts[status] = (
                status_counts.get(status, 0) + 1
            )
            cycle_count += 1

            print(
                f"cycle={cycle_count} "
                f"status={status} "
                f"proposal_id={result.get('proposal_id')}"
            )

        closed_trades = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM post_trade_reviews
            """
        ).fetchone()[0]

        open_trades = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM strategy_positions
            WHERE status = 'OPEN'
            """
        ).fetchone()[0]

        print("\nReplay complete")
        print(f"cycles={cycle_count}")
        print(f"closed_trades={closed_trades}")
        print(f"open_positions={open_trades}")
        print("status_counts=" + json.dumps(status_counts, indent=2))
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())