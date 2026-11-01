"""No-I/O plan or bounded read-only observation of a dedicated capture DB."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-db", required=True)
    parser.add_argument("--observe", action="store_true")
    args = parser.parse_args(argv)
    if not args.observe:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "read_only": True,
                    "provenance_verified": False,
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 0
    if not Path(args.receipt_db).is_file():
        parser.error("Existing capture DB required")
    try:
        import duckdb

        from nse_quant.data_platform.admission_frontier import (
            FrontierReviewRequired,
            observe_admission_frontier,
        )

        try:
            with duckdb.connect(args.receipt_db, read_only=True) as captures:
                result = observe_admission_frontier(captures)
        except FrontierReviewRequired as error:
            print(json.dumps({"status": "review_required", "reason_code": str(error)}))
            return 2
        print(json.dumps({"status": "OBSERVED_NOT_AUTHORIZED", **asdict(result)}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "ADMISSION_FRONTIER_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
