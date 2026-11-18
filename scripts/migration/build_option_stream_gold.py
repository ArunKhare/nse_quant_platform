"""Plan/apply CLI for option-chain Gold feature set v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from nse_quant.data_platform.option_stream_gold import (
    build_option_chain_features,
    initialize_option_chain_gold,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--gold-db", type=Path, required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "silver_db": str(args.silver_db),
                    "gold_db": str(args.gold_db),
                    "start_date": args.start_date,
                    "end_date": args.end_date,
                    "initialize": args.initialize,
                },
                sort_keys=True,
            )
        )
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("--actor and --code-revision are required with --execute")
    if not args.silver_db.is_file():
        parser.error("Silver database does not exist")
    if not args.gold_db.is_file() and not args.initialize:
        parser.error("--initialize required for a new Gold database")
    silver = duckdb.connect(str(args.silver_db), read_only=True)
    target = duckdb.connect(str(args.gold_db))
    try:
        if args.initialize:
            initialize_option_chain_gold(target)
        receipt = build_option_chain_features(
            silver,
            target,
            actor_id=args.actor,
            code_revision=args.code_revision,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(json.dumps({"status": "COMMITTED", **receipt}, sort_keys=True))
        return 0
    finally:
        silver.close()
        target.close()


if __name__ == "__main__":
    raise SystemExit(main())
