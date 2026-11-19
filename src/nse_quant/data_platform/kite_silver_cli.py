"""Plan-first offline normalization of one pinned Bronze variant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--capture-event-id", required=True)
    parser.add_argument("--envelope-hash", required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if args.bronze_db.resolve() == args.silver_db.resolve():
        parser.error("Separate Bronze and Silver files required")
    for value in (args.capture_event_id, args.envelope_hash):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            parser.error("Lowercase SHA-256 identities required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "normalize.kite_binary@1",
                    "capture_event_id": args.capture_event_id,
                    "envelope_hash": args.envelope_hash,
                    "target": str(args.silver_db.resolve()),
                    "inputs_verified": False,
                }
            )
        )
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Actor and code revision required")
    if not args.bronze_db.is_file():
        parser.error("Existing Bronze file required")
    if not args.silver_db.is_file() and not args.initialize:
        parser.error("Explicit --initialize required")
    import duckdb

    from nse_quant.data_platform.kite_silver import normalize_variant

    bronze = duckdb.connect(str(args.bronze_db), read_only=True)
    try:
        silver = duckdb.connect(str(args.silver_db))
        try:
            revision = normalize_variant(
                bronze,
                silver,
                capture_event_id=args.capture_event_id,
                envelope_hash=args.envelope_hash,
                actor_id=args.actor,
                code_revision=args.code_revision,
                initialize=args.initialize,
            )
        except Exception:
            print(json.dumps({"status": "FAILED", "reason_code": "NORMALIZATION_FAILED"}))
            return 1
        finally:
            silver.close()
    finally:
        bronze.close()
    print(json.dumps({"status": "COMMITTED", "revision_id": revision}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
