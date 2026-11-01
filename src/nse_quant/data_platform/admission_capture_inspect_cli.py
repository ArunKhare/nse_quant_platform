"""No-I/O default plan and explicit read-only capture inspection."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-db", required=True)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if not args.inspect:
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
    if not Path(args.receipt_db).is_file():
        parser.error("Existing receipt database required")
    import duckdb

    from nse_quant.data_platform.admission_capture_reader import read_admission_capture

    try:
        with duckdb.connect(args.receipt_db, read_only=True) as conn:
            result = read_admission_capture(conn, receipt_id=args.receipt_id)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.reassessment_history_verified else 2
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "CAPTURE_INSPECTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
