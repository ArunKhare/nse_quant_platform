"""Plan-first read-only description of one exact native reference row."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", required=True)
    parser.add_argument("--reference-db", required=True)
    parser.add_argument("--assessment-id", required=True)
    parser.add_argument("--instrument-token", required=True, type=int)
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.assessment_id):
        parser.error("Exact reference assessment pin required")
    if not 0 < args.instrument_token < 2**32:
        parser.error("Positive uint32 provider token required")
    if not args.describe:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "canonical_identity_asserted": False,
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 0
    if not all(Path(p).is_file() for p in (args.bronze_db, args.reference_db)):
        parser.error("Existing native databases required")
    try:
        import duckdb

        from nse_quant.data_platform.native_derivative_description import (
            read_native_derivative_description,
        )

        with (
            duckdb.connect(args.bronze_db, read_only=True) as bronze,
            duckdb.connect(args.reference_db, read_only=True) as silver,
        ):
            result = read_native_derivative_description(
                bronze,
                silver,
                assessment_revision_id=args.assessment_id,
                instrument_token=args.instrument_token,
            )
        summary = asdict(result)
        if result.description is not None:
            detail = asdict(result.description)
            del detail["frozen_row_json"]
            summary["description"] = detail
        print(json.dumps(summary, sort_keys=True))
        return 0 if result.status == "described" else 2
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "DERIVATIVE_DESCRIPTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
