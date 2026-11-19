"""Explicit plan-first research-only publication; no decision purpose or repair."""

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
        "publication-db",
        "artifact-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--expected-stage-fingerprint", required=True)
    parser.add_argument("--purpose", choices=["RESEARCH_ONLY"], required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-publication", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if any(
        not re.fullmatch(r"[a-f0-9]{64}", pin)
        for pin in (
            args.bundle_id,
            args.expected_stage_fingerprint,
        )
    ):
        parser.error("Exact lowercase bundle and reviewed stage-evidence SHA-256 pins required")
    inputs = [
        args.bronze_db.resolve(),
        args.frame_silver_db.resolve(),
        args.reference_silver_db.resolve(),
        args.assessment_db.resolve(),
        args.gold_db.resolve(),
        args.staging_db.resolve(),
    ]
    target, root = args.publication_db.resolve(), args.artifact_root.resolve()
    pairs = [(i, j) for i in range(6) for j in range(i + 1, 6) if (i, j) != (1, 2)]
    if target in inputs or any(inputs[i] == inputs[j] for i, j in pairs):
        parser.error("Separate input roles and dedicated publication output required")
    if any(
        path == root or root in path.parents or path in root.parents for path in [*inputs, target]
    ):
        parser.error("Artifact root must be separate from database paths")
    plan = {
        "command": "publish.research_quote_bundle@1",
        "input_databases": [str(p) for p in inputs],
        "publication_db": str(target),
        "artifact_root": str(root),
        "bundle_id": args.bundle_id,
        "expected_stage_fingerprint": args.expected_stage_fingerprint,
        "purpose": args.purpose,
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
        "inputs_verified": False,
        "decision_eligibility_asserted": False,
    }
    if not args.execute and not args.allow_publication:
        print(json.dumps({"status": "PLANNED", "plan": plan}, sort_keys=True))
        return 0
    if not args.execute or not args.allow_publication:
        parser.error("Publication requires BOTH --execute and --allow-publication")
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution identities required")
    if any(not path.is_file() for path in inputs):
        parser.error("Six existing input database files required")
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for a new publication registry")
    if any(inputs[i].samefile(inputs[j]) for i, j in pairs):
        parser.error("Input database roles alias one another")
    if target.exists() and any(target.samefile(path) for path in inputs):
        parser.error("Publication DB aliases an input")
    try:
        import duckdb

        from nse_quant.data_platform.quote_bundle_publication import publish_research_quote_bundle

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
            result = publish_research_quote_bundle(
                *sources,
                output,
                bundle_id=args.bundle_id,
                artifact_root=root,
                expected_stage_evidence_fingerprint=args.expected_stage_fingerprint,
                purpose=args.purpose,
                actor_id=args.actor,
                code_revision=args.code_revision,
                allow_publication=True,
                initialize=args.initialize,
            )
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "RESEARCH_PUBLICATION_FAILED"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
