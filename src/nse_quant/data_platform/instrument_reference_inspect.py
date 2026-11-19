"""Read-only lookup of snapshot-specific provider-token evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--silver-db", type=Path, required=True)
    parser.add_argument("--reference-revision-id", required=True)
    parser.add_argument("--instrument-token", type=int, required=True)
    args = parser.parse_args(argv)
    import duckdb

    from nse_quant.data_platform.instrument_reference_service import lookup_reference

    try:
        bronze = duckdb.connect(str(args.bronze_db), read_only=True)
        try:
            silver = duckdb.connect(str(args.silver_db), read_only=True)
            try:
                result = lookup_reference(
                    bronze,
                    silver,
                    reference_revision_id=args.reference_revision_id,
                    instrument_token=args.instrument_token,
                )
            finally:
                silver.close()
        finally:
            bronze.close()
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "REFERENCE_INSPECTION_FAILED"}))
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
