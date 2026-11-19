"""No-I/O plan or read-only independent JSONL artifact/event comparison."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", required=True)
    parser.add_argument("--support-file", required=True)
    parser.add_argument("--original-plan-file", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if re.fullmatch(r"[a-f0-9]{64}", args.plan_sha256) is None:
        parser.error("Exact reviewed original-plan SHA256 required")
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
        Path(p).is_file() for p in (args.bronze_db, args.support_file, args.original_plan_file)
    ):
        parser.error("Existing Bronze, support request and exact original plan files required")
    try:
        import duckdb

        from nse_quant.data_platform.bronze_jsonl_recompute import MAX_PLAN_BYTES, strict_json
        from nse_quant.data_platform.bronze_jsonl_support_reader import inspect_jsonl_bronze_support
        from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin

        with Path(args.original_plan_file).open("rb") as handle:
            plan_bytes = handle.read(MAX_PLAN_BYTES + 1)
        with Path(args.support_file).open("rb") as handle:
            raw = handle.read(8193)
        if len(raw) > 8192:
            raise ValueError("JSONL_SUPPORT_REQUEST_BYTE_LIMIT")
        value = strict_json(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSONL_SUPPORT_REQUEST_SCHEMA_MISMATCH")
        support = BronzeSupportPin(**value)
        with duckdb.connect(args.bronze_db, read_only=True) as bronze:
            result = inspect_jsonl_bronze_support(
                bronze,
                support=support,
                plan_bytes=plan_bytes,
                expected_plan_sha256=args.plan_sha256,
            )
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.status == "verified_jsonl_recomputation" else 2
    except Exception:
        print(
            json.dumps({"status": "ERROR", "reason_code": "JSONL_RECOMPUTATION_INSPECTION_FAILED"})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
