"""Plan-first read-only inspection of an exact stored research-IV build."""

from __future__ import annotations

import argparse
import json
import re
from contextlib import ExitStack
from pathlib import Path

SOURCE_NAMES = (
    "bronze-db",
    "frame-silver-db",
    "reference-silver-db",
    "assessment-db",
    "source-gold-db",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*SOURCE_NAMES, "archive-db"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--build-id-pin", required=True)
    parser.add_argument("--archive-fingerprint", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if any(
        re.fullmatch(r"[a-f0-9]{64}", value) is None
        for value in (args.build_id_pin, args.archive_fingerprint)
    ):
        parser.error("Exact lowercase build and reviewed archive fingerprint pins required")
    paths = [getattr(args, name.replace("-", "_")) for name in SOURCE_NAMES]
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "plan": {
                        "version": "research-iv-current-source-revalidation@1",
                        "source_paths_as_supplied": [str(path) for path in paths],
                        "archive_path_as_supplied": str(args.archive_db),
                        "build_id_pin": args.build_id_pin,
                        "expected_archive_fingerprint": args.archive_fingerprint,
                        "inputs_verified": False,
                        "current_source_checked": False,
                        "read_only_execution": True,
                        "publication_requested": False,
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    if any(not path.is_file() for path in [*paths, args.archive_db]):
        parser.error("All six input databases must already exist")
    if any(args.archive_db.samefile(path) for path in paths):
        parser.error("Research-IV archive must be separate from source databases")
    try:
        import duckdb

        from nse_quant.data_platform.research_iv_revalidation import revalidate_research_iv_build

        with ExitStack() as stack:
            opened: list[tuple[Path, duckdb.DuckDBPyConnection]] = []
            handles: list[duckdb.DuckDBPyConnection] = []
            for path in [*paths, args.archive_db]:
                conn = next((conn for old, conn in opened if path.samefile(old)), None)
                if conn is None:
                    conn = duckdb.connect(str(path), read_only=True)
                    stack.callback(conn.close)
                    opened.append((path, conn))
                handles.append(conn)
            result = revalidate_research_iv_build(
                *handles,
                build_id_pin=args.build_id_pin,
                expected_archive_fingerprint=args.archive_fingerprint,
            )
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "RESEARCH_IV_REVALIDATION_FAILED"}))
        return 1
    print(
        json.dumps(
            {
                "status": result.status,
                "reason_codes": result.reason_codes,
                "build_id": result.build_id,
                "evidence_fingerprint": result.evidence_fingerprint,
                "archived_recording_verified": result.archived_recording_verified,
                "current_source_checked": result.current_source_checked,
                "exact_recording_reproduced": result.exact_recording_reproduced,
                "publication_asserted": result.publication_asserted,
                "decision_eligibility_asserted": result.decision_eligibility_asserted,
            },
            sort_keys=True,
        )
    )
    return 0 if result.exact_recording_reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
