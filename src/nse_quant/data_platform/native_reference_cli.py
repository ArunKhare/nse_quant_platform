"""Plan-first, offline normalization of an explicitly pinned native HTTP receipt pair."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from nse_quant.data_platform.native_reference_evidence import ReferencePins


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--silver-db", type=Path, required=True)
    for name in (
        "body-capture-event-id",
        "body-envelope-hash",
        "metadata-capture-event-id",
        "metadata-envelope-hash",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    try:
        pins = ReferencePins(
            args.body_capture_event_id,
            args.body_envelope_hash,
            args.metadata_capture_event_id,
            args.metadata_envelope_hash,
        )
    except ValueError:
        parser.error("Four exact lowercase SHA-256 pins required")
    if args.bronze_db.resolve() == args.silver_db.resolve():
        parser.error("Separate Bronze and Silver files required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "normalize.kite_native_reference@1",
                    "pins": asdict(pins),
                    "inputs_verified": False,
                    "bronze_db": str(args.bronze_db.resolve()),
                    "silver_db": str(args.silver_db.resolve()),
                    "initialize": args.initialize,
                    "actor": args.actor,
                    "code_revision": args.code_revision,
                }
            )
        )
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Actor and code revision required")
    if not args.bronze_db.is_file():
        parser.error("Existing native Bronze required")
    if not args.silver_db.is_file() and not args.initialize:
        parser.error("Explicit --initialize required")
    import duckdb

    from nse_quant.data_platform.native_reference_silver import normalize_http_reference

    try:
        bronze = duckdb.connect(str(args.bronze_db), read_only=True)
        try:
            with duckdb.connect(str(args.silver_db)) as silver:
                result = normalize_http_reference(
                    bronze,
                    silver,
                    pins=pins,
                    actor_id=args.actor,
                    code_revision=args.code_revision,
                    initialize=args.initialize,
                )
        finally:
            bronze.close()
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "NATIVE_REFERENCE_FAILED"}))
        return 1
    print(json.dumps({"status": "COMMITTED", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
