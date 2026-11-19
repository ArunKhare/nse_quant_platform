"""Plan-first read-only purpose admission assessment; no decision execution."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-db", type=Path, required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument(
        "--use-case",
        required=True,
        choices=["ARCHIVED_RESEARCH_ANALYSIS", "POINT_IN_TIME_DECISION"],
    )
    parser.add_argument("--knowledge-cutoff")
    parser.add_argument("--economic-at")
    parser.add_argument("--assess", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.publication_id):
        parser.error("Exact lowercase research-publication SHA-256 required")
    clocks = []
    for raw in (args.knowledge_cutoff, args.economic_at):
        try:
            value = datetime.fromisoformat(raw) if raw is not None else None
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("NAIVE_REQUEST_TIME")
            clocks.append(value.astimezone(UTC) if value is not None else None)
        except (ValueError, TypeError, OverflowError):
            parser.error("Request times must be explicit aware ISO-8601 timestamps")
    if args.use_case == "ARCHIVED_RESEARCH_ANALYSIS" and any(value is not None for value in clocks):
        parser.error("Archival research does not support hidden as-of filtering")
    if args.use_case == "POINT_IN_TIME_DECISION" and any(value is None for value in clocks):
        parser.error("Both knowledge cutoff and economic instant are required")
    path = args.publication_db.resolve()
    if not args.assess:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "assess.publication_use@1",
                    "publication_db": str(path),
                    "publication_id": args.publication_id,
                    "use_case": args.use_case,
                    "knowledge_cutoff": clocks[0].isoformat() if clocks[0] else None,
                    "economic_at": clocks[1].isoformat() if clocks[1] else None,
                    "inputs_verified": False,
                    "decision_eligibility_asserted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if not path.is_file():
        parser.error("Existing publication registry required; no initialization supported")
    try:
        import duckdb

        from nse_quant.data_platform.publication_admission import (
            AdmissionRequest,
            assess_publication_use,
        )

        connection = duckdb.connect(str(path), read_only=True)
        try:
            receipt = assess_publication_use(
                connection,
                publication_id=args.publication_id,
                request=AdmissionRequest(args.use_case, clocks[0], clocks[1]),
            )
        finally:
            connection.close()
        report = {
            "receipt_id": receipt.receipt_id,
            "policy_version": receipt.policy_version,
            "input_sha256": receipt.input_sha256,
            "publication_id": receipt.publication_id,
            "bundle_id": receipt.bundle_id,
            "status": receipt.status,
            "reason_codes": receipt.reason_codes,
            "research_analysis_permitted": receipt.research_analysis_permitted,
            "decision_eligibility_asserted": False,
            "availability_evidence_verified": False,
            "economic_validity_verified": False,
            "source_current_checked": False,
            "replay_authenticity_asserted": False,
        }
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "PUBLICATION_ADMISSION_FAILED"}))
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if receipt.research_analysis_permitted else 2


if __name__ == "__main__":
    raise SystemExit(main())
