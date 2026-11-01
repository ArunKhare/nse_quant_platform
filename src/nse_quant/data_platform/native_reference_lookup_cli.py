"""Plan-first offline inspection of current, explicitly pinned reference evidence."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

COMMAND_VERSION = "inspect.kite_native_reference@1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--assessment-revision-id", required=True)
    parser.add_argument("--instrument-token", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.assessment_revision_id):
        parser.error("Exact lowercase SHA-256 assessment revision required")
    if not 0 < args.instrument_token < 2**32:
        parser.error("Provider token must be in 1..4294967295")
    bronze_path = args.bronze_db.resolve()
    silver_path = args.silver_db.resolve()
    if bronze_path == silver_path:
        parser.error("Separate Bronze and Silver files required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": COMMAND_VERSION,
                    "bronze_db": str(bronze_path),
                    "silver_db": str(silver_path),
                    "assessment_revision_id": args.assessment_revision_id,
                    "instrument_token": args.instrument_token,
                    "inputs_verified": False,
                    "read_only": True,
                    "publication_asserted": False,
                    "historical_validity_asserted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if not bronze_path.is_file() or not silver_path.is_file():
        parser.error("Existing native Bronze and Silver database files required")
    if bronze_path.samefile(silver_path):
        parser.error("Separate Bronze and Silver files required")
    try:
        import duckdb

        from nse_quant.data_platform.native_reference_reader import lookup_native_reference

        bronze = duckdb.connect(str(bronze_path), read_only=True)
        try:
            silver = duckdb.connect(str(silver_path), read_only=True)
            try:
                result = lookup_native_reference(
                    bronze,
                    silver,
                    assessment_revision_id=args.assessment_revision_id,
                    instrument_token=args.instrument_token,
                )
            finally:
                silver.close()
        finally:
            bronze.close()
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "REFERENCE_LOOKUP_FAILED"}))
        return 1
    print(json.dumps({"command": COMMAND_VERSION, **asdict(result)}, sort_keys=True))
    return 0 if result.status == "matched" else 2


if __name__ == "__main__":
    raise SystemExit(main())
