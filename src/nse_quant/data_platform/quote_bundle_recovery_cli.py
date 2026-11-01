"""Plan-first, nonexecuting targeted bundle recovery inspection."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

MAX_REPORT_BYTES = 2_097_152


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-db", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--max-history", type=int, default=128)
    parser.add_argument("--max-jobs", type=int, default=128)
    parser.add_argument("--max-directory-entries", type=int, default=128)
    parser.add_argument("--max-artifact-bytes", type=int, default=4_194_304)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.bundle_id):
        parser.error("Exact lowercase SHA-256 bundle pin required")
    for value, cap in (
        (args.max_history, 1001),
        (args.max_jobs, 1000),
        (args.max_directory_entries, 1000),
        (args.max_artifact_bytes, 4_194_304),
    ):
        if not 1 <= value <= cap:
            parser.error("Inspection bounds must be positive and within hard limits")
    database, root = args.staging_db.resolve(), args.artifact_root.resolve()
    if database == root or root in database.parents or database in root.parents:
        parser.error("Artifact root must be separate from metadata DB")
    policy = {
        "max_history": args.max_history,
        "max_jobs": args.max_jobs,
        "max_directory_entries": args.max_directory_entries,
        "max_artifact_bytes": args.max_artifact_bytes,
    }
    if not args.inspect:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "inspect.bundle_recovery@1",
                    "staging_db": str(database),
                    "artifact_root": str(root),
                    "bundle_id": args.bundle_id,
                    "policy": policy,
                    "inputs_verified": False,
                    "execution_permitted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if not database.is_file():
        parser.error("Existing staging database required; no initialization supported")
    try:
        import duckdb

        from nse_quant.data_platform.quote_bundle_recovery import (
            RecoveryPolicy,
            inspect_bundle_recovery,
        )

        connection = duckdb.connect(str(database), read_only=True)
        try:
            plan = inspect_bundle_recovery(
                connection,
                bundle_id=args.bundle_id,
                artifact_root=root,
                policy=RecoveryPolicy(**policy),
            )
        finally:
            connection.close()
        output = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(output.encode()) > MAX_REPORT_BYTES:
            raise ValueError("RECOVERY_REPORT_LIMIT")
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "RECOVERY_INSPECTION_FAILED"}))
        return 1
    print(output)
    return 0 if plan.status == "NO_TARGET_FINDINGS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
