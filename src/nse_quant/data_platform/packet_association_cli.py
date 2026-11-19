"""Plan-first offline persistence of one pinned packet/reference assessment."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bronze-db", "frame-silver-db", "reference-silver-db", "assessment-db"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frame-revision-id", required=True)
    parser.add_argument("--reference-assessment-revision-id", required=True)
    parser.add_argument("--packet-ordinal", type=int, required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    for pin in (args.frame_revision_id, args.reference_assessment_revision_id):
        if not re.fullmatch(r"[a-f0-9]{64}", pin):
            parser.error("Exact lowercase SHA-256 pins required")
    if not 0 <= args.packet_ordinal < 4096:
        parser.error("Packet ordinal must be in 0..4095")
    inputs = [
        args.bronze_db.resolve(),
        args.frame_silver_db.resolve(),
        args.reference_silver_db.resolve(),
    ]
    target = args.assessment_db.resolve()
    if target in inputs or inputs[0] in inputs[1:]:
        parser.error("Separate Bronze, input Silver and output assessment files required")
    plan = {
        "command": "assess.packet_reference@1",
        "inputs_verified": False,
        "bronze_db": str(inputs[0]),
        "frame_silver_db": str(inputs[1]),
        "reference_silver_db": str(inputs[2]),
        "assessment_db": str(target),
        "frame_revision_id": args.frame_revision_id,
        "packet_ordinal": args.packet_ordinal,
        "reference_assessment_revision_id": args.reference_assessment_revision_id,
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, sort_keys=True))
        return 0
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution identities required")
    if any(not path.is_file() for path in inputs):
        parser.error("Existing input databases required")
    if not target.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for new assessment DB")
    if any(inputs[0].samefile(path) for path in inputs[1:]):
        parser.error("Separate Bronze and Silver files required")
    if target.exists() and any(target.samefile(path) for path in inputs):
        parser.error("Assessment DB aliases an input")
    try:
        from contextlib import ExitStack

        import duckdb

        from nse_quant.data_platform.packet_association_silver import persist_packet_association

        with ExitStack() as stack:
            connections = {}
            sources = []
            for path in inputs:
                # Reuse frame/reference Silver connection when paths are identical.
                if path not in connections:
                    conn = duckdb.connect(str(path), read_only=True)
                    stack.callback(conn.close)
                    connections[path] = conn
                sources.append(connections[path])
            output = duckdb.connect(str(target))
            stack.callback(output.close)
            result = persist_packet_association(
                *sources,
                output,
                frame_revision_id=args.frame_revision_id,
                packet_ordinal=args.packet_ordinal,
                reference_assessment_revision_id=args.reference_assessment_revision_id,
                actor_id=args.actor,
                code_revision=args.code_revision,
                initialize=args.initialize,
            )
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "ASSOCIATION_ASSESSMENT_FAILED"}))
        return 1
    print(json.dumps({"execution_status": "COMMITTED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
