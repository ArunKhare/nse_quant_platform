"""Plan-first offline instrument file import and pinned normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from nse_quant.data_platform.instrument_reference import MAX_ARTIFACT_BYTES


def _hash(value: str) -> str:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise argparse.ArgumentTypeError("Lowercase SHA-256 required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    imp = sub.add_parser("import-file")
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--import-session-id", required=True)
    imp.add_argument("--source-record-id", required=True)
    norm = sub.add_parser("normalize")
    norm.add_argument("--silver-db", type=Path, required=True)
    norm.add_argument("--capture-event-id", type=_hash, required=True)
    norm.add_argument("--envelope-hash", type=_hash, required=True)
    for command in (imp, norm):
        command.add_argument("--bronze-db", type=Path, required=True)
        command.add_argument("--actor", default="manual")
        command.add_argument("--code-revision", default="")
        command.add_argument("--execute", action="store_true")
        command.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    raw = None
    plan: dict[str, object] = {
        "operation": args.operation,
        "plan_version": 1,
        "bronze_db": str(args.bronze_db.resolve()),
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
    }
    if args.operation == "import-file":
        if args.input.resolve() == args.bronze_db.resolve():
            parser.error("Input and target must be different files")
        if not args.import_session_id.strip() or not args.source_record_id.strip():
            parser.error("Explicit receipt identities required")
        with args.input.open("rb") as handle:
            raw = handle.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            parser.error("Artifact exceeds 16 MiB")
        plan.update(
            {
                "import_session_id": args.import_session_id,
                "source_record_id": args.source_record_id,
                "artifact_hash": hashlib.sha256(raw).hexdigest(),
                "artifact_bytes": len(raw),
                "original_provider_receipt_known": False,
            }
        )
    else:
        if args.silver_db.resolve() == args.bronze_db.resolve():
            parser.error("Separate Bronze and Silver files required")
        plan.update(
            {
                "silver_db": str(args.silver_db.resolve()),
                "capture_event_id": args.capture_event_id,
                "envelope_hash": args.envelope_hash,
                "inputs_verified": False,
            }
        )
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}))
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Actor and code revision required")
    if args.operation == "normalize" and not args.bronze_db.is_file():
        parser.error("Existing Bronze file required")
    target = args.bronze_db if args.operation == "import-file" else args.silver_db
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for new target")
    import duckdb

    from nse_quant.data_platform.instrument_reference_service import (
        import_reference_artifact,
        normalize_reference,
    )

    try:
        if args.operation == "import-file":
            with duckdb.connect(str(args.bronze_db)) as conn:
                assert raw is not None
                event, envelope, conflict = import_reference_artifact(
                    conn,
                    raw,
                    import_session_id=args.import_session_id,
                    source_record_id=args.source_record_id,
                    actor_id=args.actor,
                    code_revision=args.code_revision,
                    initialize=args.initialize,
                )
            output = {
                "capture_event_id": event,
                "envelope_hash": envelope,
                "receipt_conflict_requires_review": conflict,
            }
        else:
            bronze = duckdb.connect(str(args.bronze_db), read_only=True)
            try:
                with duckdb.connect(str(args.silver_db)) as silver:
                    revision = normalize_reference(
                        bronze,
                        silver,
                        capture_event_id=args.capture_event_id,
                        envelope_hash=args.envelope_hash,
                        actor_id=args.actor,
                        code_revision=args.code_revision,
                        initialize=args.initialize,
                    )
            finally:
                bronze.close()
            output = {"reference_revision_id": revision}
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "REFERENCE_OPERATION_FAILED"}))
        return 1
    status = (
        "COMMITTED_WITH_CONFLICTS"
        if output.get("receipt_conflict_requires_review")
        else "COMMITTED"
    )
    print(json.dumps({"status": status, **output}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
