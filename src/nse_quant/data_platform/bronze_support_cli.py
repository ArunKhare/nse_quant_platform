"""No-I/O plan; explicit read-only pinned support storage observation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if not args.inspect:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "read_only": True,
                    "identity_verified": False,
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 0
    if not Path(args.bronze_db).is_file() or not Path(args.request_file).is_file():
        parser.error("Existing Bronze database and reviewed request file required")
    try:
        import duckdb

        from nse_quant.data_platform.bronze_support_reader import (
            BronzeSupportPin,
            IngestAuditExpectation,
            _json,
            inspect_bronze_support,
        )

        with Path(args.request_file).open("rb") as handle:
            raw = handle.read(8193)
        if len(raw) > 8192:
            raise ValueError("SUPPORT_REQUEST_FILE_LIMIT")
        request = _json(raw.decode("utf-8"))
        if not isinstance(request, dict) or set(request) != {"support", "expected_audit"}:
            raise ValueError("SUPPORT_REQUEST_SCHEMA_MISMATCH")
        support = BronzeSupportPin(**request["support"])
        expectation = IngestAuditExpectation(**request["expected_audit"])
        with duckdb.connect(args.bronze_db, read_only=True) as bronze:
            result = inspect_bronze_support(bronze, support=support, expected_audit=expectation)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.status == "verified_storage_evidence" else 2
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "BRONZE_SUPPORT_INSPECTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
