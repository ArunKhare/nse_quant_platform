"""Plan-first read-only exact capture/request revalidation."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-db", required=True)
    parser.add_argument("--receipt-db", required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument(
        "--use-case",
        required=True,
        choices=["ARCHIVED_RESEARCH_ANALYSIS", "POINT_IN_TIME_DECISION"],
    )
    parser.add_argument("--knowledge-cutoff")
    parser.add_argument("--economic-at")
    parser.add_argument("--revalidate", action="store_true")
    args = parser.parse_args(argv)
    for pin in (args.publication_id, args.receipt_id):
        if re.fullmatch(r"[a-f0-9]{64}", pin) is None:
            parser.error("Exact lowercase SHA256 pins required")
    clocks: list[datetime | None] = []
    for raw in (args.knowledge_cutoff, args.economic_at):
        try:
            clock = datetime.fromisoformat(raw) if raw is not None else None
            if clock is not None and (clock.tzinfo is None or clock.utcoffset() is None):
                raise ValueError("AWARE_REQUEST_REQUIRED")
        except (ValueError, TypeError, OverflowError):
            parser.error("Explicit aware request timestamps required")
        clocks.append(clock)
    if args.use_case == "ARCHIVED_RESEARCH_ANALYSIS" and any(x is not None for x in clocks):
        parser.error("Archival research has no time filters")
    if args.use_case == "POINT_IN_TIME_DECISION" and any(x is None for x in clocks):
        parser.error("Both point-in-time axes required")
    if not args.revalidate:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "read_only": True,
                    "current_request_checked": False,
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 0
    if not all(Path(p).is_file() for p in (args.publication_db, args.receipt_db)):
        parser.error("Existing separate databases required")
    try:
        import duckdb

        from nse_quant.data_platform.admission_revalidation import (
            revalidate_captured_publication_use,
        )
        from nse_quant.data_platform.publication_admission import AdmissionRequest

        with (
            duckdb.connect(args.publication_db, read_only=True) as publications,
            duckdb.connect(args.receipt_db, read_only=True) as captures,
        ):
            result = revalidate_captured_publication_use(
                publications,
                captures,
                publication_id=args.publication_id,
                receipt_id=args.receipt_id,
                request=AdmissionRequest(args.use_case, clocks[0], clocks[1]),
            )
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.status == "matched_research_input" else 2
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "ADMISSION_REVALIDATION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
