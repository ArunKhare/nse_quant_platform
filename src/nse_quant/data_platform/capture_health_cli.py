"""Inspect native capture and optionally publish an audited, nonexecuting recovery plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from nse_quant.data_platform.capture_health import InspectionLimits, inspect_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--max-segments", type=int, default=4096)
    parser.add_argument("--max-total-bytes", type=int, default=1_073_741_824)
    parser.add_argument("--publish-plan", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args(argv)
    limits = InspectionLimits(max_segments=args.max_segments, max_total_bytes=args.max_total_bytes)
    report = inspect_capture(args.session_dir, limits=limits)
    result = {"health": asdict(report), "recovery_plan": report.recovery_plan()}
    if args.publish_plan:
        if args.output_root is None or not args.actor.strip() or not args.code_revision.strip():
            parser.error("Plan publication requires output root, actor and code revision")
        source = args.session_dir.resolve()
        target = args.output_root.resolve()
        if target == source or source in target.parents:
            parser.error("Inspection output must be outside the source session")
        import duckdb

        from nse_quant.data_platform.audit import AuditLedger
        from nse_quant.data_platform.manifests import ManifestStore

        verified = inspect_capture(source, limits=limits)
        if verified.source_fingerprint != report.source_fingerprint:
            parser.error("Source changed; inspect again before publishing a review plan")
        directory = target / ("capture_review_" + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        conn = duckdb.connect(str(directory / "inspection_audit.duckdb"))
        try:
            ledger = AuditLedger(conn)
            ledger.initialize()
            manifests = ManifestStore(directory / "manifests")
            scope = json.dumps(
                {"source_fingerprint": report.source_fingerprint, "limits": asdict(limits)},
                sort_keys=True,
            ).encode()
            manifests.put(scope)
            job = ledger.plan_job(
                command_name="inspect.capture_review_plan@1",
                actor_id=args.actor,
                scope_ref="sha256:" + hashlib.sha256(scope).hexdigest(),
                code_revision=args.code_revision,
                config_hash=hashlib.sha256(b"read-only-capture-review-v1").hexdigest(),
            )
            with ledger.execution(job):
                payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
                manifests.put(payload)
                for name, value in (
                    ("health.json", result["health"]),
                    ("recovery_plan.json", result["recovery_plan"]),
                ):
                    with (directory / name).open("x", encoding="utf-8") as handle:
                        json.dump(value, handle, sort_keys=True, indent=2)
                (directory / "review_receipt.json").write_text(
                    json.dumps(
                        {
                            "job_id": job,
                            "report_sha256": hashlib.sha256(payload).hexdigest(),
                            "source_fingerprint": report.source_fingerprint,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            result["publication"] = {"directory": str(directory), "job_id": job}
        finally:
            conn.close()
    print(json.dumps(result, indent=2))
    return 2 if args.require_clean and not report.automatic_ingestion_allowed else 0


if __name__ == "__main__":
    raise SystemExit(main())
