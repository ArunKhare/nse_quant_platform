"""Plan-first native Gold quote build execution; no data migration or publication."""

from __future__ import annotations

import argparse
import json
import re
from contextlib import ExitStack
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bronze-db", "frame-silver-db", "reference-silver-db", "assessment-db", "gold-db"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--assessment-revision-id", required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.assessment_revision_id):
        parser.error("Exact lowercase SHA-256 assessment pin required")
    inputs = [
        args.bronze_db.resolve(),
        args.frame_silver_db.resolve(),
        args.reference_silver_db.resolve(),
        args.assessment_db.resolve(),
    ]
    target = args.gold_db.resolve()
    if inputs[0] in inputs[1:] or inputs[3] in inputs[:3] or target in inputs:
        parser.error("Separate Bronze, assessment and Gold files required")
    plan = {
        "command": "build.provider_quote_prices@1",
        "inputs_verified": False,
        "bronze_db": str(inputs[0]),
        "frame_silver_db": str(inputs[1]),
        "reference_silver_db": str(inputs[2]),
        "assessment_db": str(inputs[3]),
        "gold_db": str(target),
        "assessment_revision_id": args.assessment_revision_id,
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
        "publication_requested": False,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, sort_keys=True))
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution identities required")
    if any(not path.is_file() for path in inputs):
        parser.error("Four existing input database files required")
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for a new dedicated Gold DB")
    if any(inputs[0].samefile(path) for path in inputs[1:]):
        parser.error("Bronze aliases another input")
    if any(inputs[3].samefile(path) for path in inputs[:3]):
        parser.error("Assessment DB aliases another input")
    if target.exists() and any(target.samefile(path) for path in inputs):
        parser.error("Gold DB aliases an input")
    try:
        import duckdb

        from nse_quant.data_platform.gold_quote_store import persist_quote_price_build

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
            receipt = persist_quote_price_build(
                *sources,
                output,
                assessment_revision_id=args.assessment_revision_id,
                actor_id=args.actor,
                code_revision=args.code_revision,
                initialize=args.initialize,
            )
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "GOLD_QUOTE_BUILD_FAILED"}))
        return 1
    print(json.dumps({"execution_status": "COMMITTED", **receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
