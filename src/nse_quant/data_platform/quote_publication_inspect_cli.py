"""Plan-first inspection of an archived RESEARCH_ONLY publication, never live sources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-db", type=Path, required=True)
    parser.add_argument("--publication-id", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.publication_id):
        parser.error("Exact lowercase SHA-256 research-publication pin required")
    path = args.publication_db.resolve()
    if not args.inspect:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "command": "inspect.research_publication@1",
                    "publication_db": str(path),
                    "publication_id": args.publication_id,
                    "inputs_verified": False,
                    "source_current_checked": False,
                    "decision_eligibility_asserted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    if not path.is_file():
        parser.error("Existing registry required; initialization is not supported")
    try:
        import duckdb

        from nse_quant.data_platform.quote_publication_reader import read_research_publication

        connection = duckdb.connect(str(path), read_only=True)
        try:
            evidence = read_research_publication(connection, publication_id=args.publication_id)
        finally:
            connection.close()
        # Do not print manifest features, raw payloads, paths from rows or exception text.
        summary = {
            "reader_version": evidence.reader_version,
            "publication_id": evidence.publication_id,
            "status": evidence.status,
            "reason_code": evidence.reason_code,
            "purpose": evidence.purpose,
            "bundle_id": evidence.bundle_id,
            "publication_recorded_at": evidence.publication_recorded_at,
            "origin_audit_success_recorded_at": evidence.origin_audit_success_recorded_at,
            "clock_semantics": evidence.clock_semantics,
            "successful_attempt_count": len(evidence.successful_attempt_job_ids),
            "evidence_fingerprint": evidence.evidence_fingerprint,
            "research_publication_verified": evidence.research_publication_verified,
            "availability_time_known": False,
            "source_current_checked": False,
            "historical_validity_asserted": False,
            "decision_eligibility_asserted": False,
        }
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "PUBLICATION_INSPECTION_FAILED"}))
        return 1
    print(json.dumps(summary, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if evidence.research_publication_verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
