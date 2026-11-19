"""Plan-first audited bundle staging; no publication, adoption or migration."""

from __future__ import annotations

import argparse
import json
import re
from contextlib import ExitStack
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "bronze-db",
        "frame-silver-db",
        "reference-silver-db",
        "assessment-db",
        "gold-db",
        "staging-db",
        "artifact-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--build-id", action="append", required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    pins = tuple(sorted(args.build_id))
    if (
        not 1 <= len(pins) <= 64
        or len(set(pins)) != len(pins)
        or any(not re.fullmatch(r"[a-f0-9]{64}", pin) for pin in pins)
    ):
        parser.error("1..64 explicit unique lowercase SHA-256 build pins required")
    inputs = [
        args.bronze_db.resolve(),
        args.frame_silver_db.resolve(),
        args.reference_silver_db.resolve(),
        args.assessment_db.resolve(),
        args.gold_db.resolve(),
    ]
    target, artifacts = args.staging_db.resolve(), args.artifact_root.resolve()
    pairs = [(i, j) for i in range(5) for j in range(i + 1, 5) if (i, j) != (1, 2)]
    if target in inputs or any(inputs[i] == inputs[j] for i, j in pairs):
        parser.error(
            "Separate input roles and staging DB required; frame/reference Silver may share"
        )
    if any(
        path == artifacts or artifacts in path.parents or path in artifacts.parents
        for path in [*inputs, target]
    ):
        parser.error("Dedicated artifact root must be separate from all database paths")
    plan = {
        "command": "stage.quote_feature_bundle@1",
        "build_ids": pins,
        "input_databases": [str(path) for path in inputs],
        "staging_db": str(target),
        "artifact_root": str(artifacts),
        "initialize": args.initialize,
        "actor": args.actor,
        "code_revision": args.code_revision,
        "inputs_verified": False,
        "publication_requested": False,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, sort_keys=True))
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution identities required")
    if any(not path.is_file() for path in inputs):
        parser.error("Five existing input database files required")
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for a new dedicated staging DB")
    if any(inputs[i].samefile(inputs[j]) for i, j in pairs):
        parser.error("Input database roles alias one another")
    if target.exists() and any(target.samefile(path) for path in inputs):
        parser.error("Staging DB aliases an input")
    try:
        import duckdb

        from nse_quant.data_platform.quote_bundle_staging import stage_quote_bundle

        with ExitStack() as stack:
            opened: list[tuple[Path, duckdb.DuckDBPyConnection]] = []
            sources = []
            for path in inputs:
                connection = next((conn for prior, conn in opened if path.samefile(prior)), None)
                if connection is None:
                    connection = duckdb.connect(str(path), read_only=True)
                    stack.callback(connection.close)
                    opened.append((path, connection))
                sources.append(connection)
            output = duckdb.connect(str(target))
            stack.callback(output.close)
            result = stage_quote_bundle(
                *sources,
                output,
                build_ids=pins,
                artifact_root=artifacts,
                actor_id=args.actor,
                code_revision=args.code_revision,
                initialize=args.initialize,
            )
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "BUNDLE_STAGE_FAILED"}))
        return 1
    print(json.dumps({"execution_status": "COMMITTED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
