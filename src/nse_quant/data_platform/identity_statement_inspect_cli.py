"""No-I/O plan or exact recorded untrusted statement content inspection."""

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
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--original-plan-file", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if any(
        re.fullmatch(r"[a-f0-9]{64}", pin) is None for pin in (args.assertion_id, args.plan_sha256)
    ):
        parser.error("Exact assertion and original-plan SHA256 pins required")
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
    if not all(
        Path(p).is_file()
        for p in (args.identity_db, args.bronze_db, args.request_file, args.original_plan_file)
    ):
        parser.error("Existing databases, typed request and original import plan required")
    try:
        import duckdb

        from nse_quant.data_platform.bronze_jsonl_recompute import MAX_PLAN_BYTES
        from nse_quant.data_platform.identity_statement_document import strict_json
        from nse_quant.data_platform.identity_statement_reader import (
            inspect_recorded_statement_content,
        )
        from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

        with Path(args.request_file).open("rb") as handle:
            request_raw = handle.read(16385)
        if len(request_raw) > 16384:
            raise ValueError("STATEMENT_REQUEST_FILE_LIMIT")
        value = strict_json(request_raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("STATEMENT_REQUEST_FILE_SCHEMA")
        request = UnderlyingAssertionRequest(**value)
        with Path(args.original_plan_file).open("rb") as handle:
            plan_bytes = handle.read(MAX_PLAN_BYTES + 1)
        with (
            duckdb.connect(args.identity_db, read_only=True) as registry,
            duckdb.connect(args.bronze_db, read_only=True) as bronze,
        ):
            result = inspect_recorded_statement_content(
                registry,
                bronze,
                assertion_id=args.assertion_id,
                request=request,
                record_id=args.record_id,
                original_plan=plan_bytes,
                expected_plan_sha256=args.plan_sha256,
            )
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.status == "matched_untrusted_statement_support" else 2
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "IDENTITY_STATEMENT_CONTENT_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
