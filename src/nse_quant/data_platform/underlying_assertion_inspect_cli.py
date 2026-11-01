"""No-I/O plan or read-only archived assertion recording inspection."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-db", required=True)
    parser.add_argument("--assertion-id", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if re.fullmatch(r"[a-f0-9]{64}", args.assertion_id) is None:
        parser.error("Exact assertion SHA256 pin required")
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
    if not Path(args.identity_db).is_file():
        parser.error("Existing identity assertion database required")
    try:
        import duckdb

        from nse_quant.data_platform.underlying_assertion_reader import (
            read_underlying_assertion_recording,
        )

        with duckdb.connect(args.identity_db, read_only=True) as registry:
            result = read_underlying_assertion_recording(registry, assertion_id=args.assertion_id)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.registry_history_verified else 2
    except Exception:
        print(
            json.dumps({"status": "ERROR", "reason_code": "UNDERLYING_RECORDING_INSPECTION_FAILED"})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
