"""Plan-first audited receipt capture, not strategy/decision execution or publication."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-db", type=Path, required=True)
    parser.add_argument("--receipt-db", type=Path, required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument(
        "--use-case",
        required=True,
        choices=["ARCHIVED_RESEARCH_ANALYSIS", "POINT_IN_TIME_DECISION"],
    )
    parser.add_argument("--knowledge-cutoff")
    parser.add_argument("--economic-at")
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.publication_id):
        parser.error("Exact publication SHA-256 required")
    clocks: list[datetime | None] = []
    for raw in (args.knowledge_cutoff, args.economic_at):
        try:
            value = datetime.fromisoformat(raw) if raw is not None else None
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("NAIVE_REQUEST_TIME")
            clocks.append(value.astimezone(UTC) if value is not None else None)
        except (ValueError, TypeError, OverflowError):
            parser.error("Explicit aware ISO-8601 request timestamps required")
    if args.use_case == "ARCHIVED_RESEARCH_ANALYSIS" and any(value is not None for value in clocks):
        parser.error("Archival research is not an as-of request")
    if args.use_case == "POINT_IN_TIME_DECISION" and any(value is None for value in clocks):
        parser.error("Both point-in-time request axes required")
    source, target = args.publication_db.resolve(), args.receipt_db.resolve()
    if source == target:
        parser.error("Separate publication and receipt databases required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "capture.publication_admission@1",
                    "publication_db": str(source),
                    "receipt_db": str(target),
                    "publication_id": args.publication_id,
                    "use_case": args.use_case,
                    "knowledge_cutoff": clocks[0].isoformat() if clocks[0] else None,
                    "economic_at": clocks[1].isoformat() if clocks[1] else None,
                    "actor": args.actor,
                    "code_revision": args.code_revision,
                    "initialize": args.initialize,
                    "inputs_verified": False,
                    "decision_eligibility_asserted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution identities required")
    if not source.is_file():
        parser.error("Existing publication registry required")
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for a new receipt DB")
    if target.exists() and source.samefile(target):
        parser.error("Receipt DB aliases publication source")
    try:
        import duckdb

        from nse_quant.data_platform.admission_capture import capture_publication_admission
        from nse_quant.data_platform.publication_admission import AdmissionRequest

        publication = duckdb.connect(str(source), read_only=True)
        try:
            receipt_db = duckdb.connect(str(target))
            try:
                result = capture_publication_admission(
                    publication,
                    receipt_db,
                    publication_id=args.publication_id,
                    request=AdmissionRequest(args.use_case, clocks[0], clocks[1]),
                    actor_id=args.actor,
                    code_revision=args.code_revision,
                    initialize=args.initialize,
                )
            finally:
                receipt_db.close()
        finally:
            publication.close()
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "ADMISSION_CAPTURE_FAILED"}))
        return 1
    print(json.dumps({"execution_status": "COMMITTED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
