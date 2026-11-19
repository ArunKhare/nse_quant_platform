"""Read-only CLI for availability-aware Gold feature retrieval and replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb

from nse_quant.data_platform.gold_feature_retrieval import (
    replay_gold_feature,
    retrieve_gold_feature,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-db", type=Path, required=True)
    parser.add_argument("--underlying", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--bundle-file", type=Path)
    parser.add_argument("--expected-bundle-sha256")
    args = parser.parse_args(argv)
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if args.bundle_file:
        if not args.expected_bundle_sha256:
            parser.error("--expected-bundle-sha256 required with --bundle-file")
        bundle = json.loads(args.bundle_file.read_text(encoding="utf-8"))
        receipt = replay_gold_feature(
            duckdb.connect(str(args.gold_db), read_only=True),
            bundle=bundle,
            expected_bundle_sha256=args.expected_bundle_sha256,
        )
    else:
        receipt = retrieve_gold_feature(
            duckdb.connect(str(args.gold_db), read_only=True),
            underlying=args.underlying,
            as_of=as_of,
        )
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
