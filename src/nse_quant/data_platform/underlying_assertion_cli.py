"""No-I/O plan; explicitly requested unverified identity assertion recording."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", required=True)
    parser.add_argument("--identity-db", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--actor", default="")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-assertion-recording", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "writes_performed": False,
                    "identity_verified": False,
                    "decision_eligibility_asserted": False,
                }
            )
        )
        return 0
    if not args.allow_assertion_recording:
        parser.error("Execution requires --allow-assertion-recording")
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Explicit actor and code revision required")
    source, target = Path(args.bronze_db), Path(args.identity_db)
    if not source.is_file() or not Path(args.request_file).is_file():
        parser.error("Existing Bronze database and request file required")
    if not target.exists() and not args.initialize:
        parser.error("New target requires --initialize")
    if not target.parent.is_dir():
        parser.error("Target parent must already exist")
    if target.exists() and source.samefile(target):
        parser.error("Separate identity assertion database required")
    try:
        import duckdb

        from nse_quant.data_platform.underlying_assertion import (
            MAX_ASSERTION_BYTES,
            UnderlyingAssertionRequest,
            strict_json,
        )
        from nse_quant.data_platform.underlying_assertion_store import record_underlying_assertion

        with Path(args.request_file).open("rb") as handle:
            raw = handle.read(MAX_ASSERTION_BYTES + 1)
        if len(raw) > MAX_ASSERTION_BYTES:
            raise ValueError("ASSERTION_REQUEST_FILE_BYTE_LIMIT")
        value = strict_json(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("ASSERTION_REQUEST_FILE_SCHEMA_MISMATCH")
        request = UnderlyingAssertionRequest(**value)
        with (
            duckdb.connect(str(source), read_only=True) as bronze,
            duckdb.connect(str(target)) as registry,
        ):
            result = record_underlying_assertion(
                bronze,
                registry,
                request=request,
                actor_id=args.actor,
                code_revision=args.code_revision,
                initialize=args.initialize,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "ERROR", "reason_code": "UNDERLYING_ASSERTION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
