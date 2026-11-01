"""No-I/O planning or explicit read-only recorded-assertion/current-storage checks."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-db", required=True)
    parser.add_argument("--bronze-db", required=True)
    parser.add_argument("--assertion-id", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--revalidate", action="store_true")
    args = parser.parse_args(argv)
    if re.fullmatch(r"[a-f0-9]{64}", args.assertion_id) is None:
        parser.error("Exact assertion SHA256 pin required")
    if not args.revalidate:
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
    if not all(Path(p).is_file() for p in (args.identity_db, args.bronze_db, args.request_file)):
        parser.error("Existing registry, Bronze and reviewed request file required")
    try:
        import duckdb

        from nse_quant.data_platform.bronze_support_reader import IngestAuditExpectation
        from nse_quant.data_platform.underlying_assertion import (
            UnderlyingAssertionRequest,
            strict_json,
        )
        from nse_quant.data_platform.underlying_support_revalidation import (
            revalidate_underlying_assertion_support,
        )

        with Path(args.request_file).open("rb") as handle:
            raw = handle.read(32769)
        if len(raw) > 32768:
            raise ValueError("REVALIDATION_REQUEST_FILE_LIMIT")
        value = strict_json(raw.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {"assertion_request", "expected_audit"}:
            raise ValueError("REVALIDATION_REQUEST_FILE_SCHEMA_MISMATCH")
        request = UnderlyingAssertionRequest(**value["assertion_request"])
        expected = IngestAuditExpectation(**value["expected_audit"])
        with (
            duckdb.connect(args.identity_db, read_only=True) as registry,
            duckdb.connect(args.bronze_db, read_only=True) as bronze,
        ):
            result = revalidate_underlying_assertion_support(
                registry,
                bronze,
                assertion_id=args.assertion_id,
                request=request,
                expected_audit=expected,
            )
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.status == "verified_recording_and_current_storage" else 2
    except Exception:
        print(
            json.dumps({"status": "ERROR", "reason_code": "UNDERLYING_SUPPORT_REVALIDATION_FAILED"})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
