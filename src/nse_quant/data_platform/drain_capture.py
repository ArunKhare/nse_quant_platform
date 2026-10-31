"""Audited import of verified, completed raw-capture segments into native Bronze."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from nse_quant.data_platform.native_kite_capture import verify_sealed_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    source = args.session_dir.resolve()
    for target in (args.bronze_db.resolve(), args.manifest_root.resolve()):
        if source == target or source in target.parents:
            parser.error("Ingestion outputs must be outside the sealed capture session")
    segments = verify_sealed_session(source)
    final = json.loads((source / "session_final.json").read_text(encoding="utf-8"))
    import duckdb

    conn = duckdb.connect(str(source / "audit.duckdb"), read_only=True)
    try:
        state = conn.execute(
            "SELECT e.state FROM medallion_audit.job_events e "
            "JOIN medallion_audit.jobs j ON j.job_id = e.job_id "
            "WHERE j.job_id = ? AND j.command_name = 'capture.kite_raw@1' "
            "ORDER BY e.event_index DESC LIMIT 1",
            [final["audit_job_id"]],
        ).fetchone()
        if state is None or state[0] != "SUCCEEDED":
            parser.error("Capture audit has not completed successfully; recovery review required")
    finally:
        conn.close()
    plan = {
        "command": "ingest.kite_segments@1",
        "session_id": final["capture_session_id"],
        "segments": [{"file": segment.path.name, "sha256": segment.sha256} for segment in segments],
        "target_db": str(args.bronze_db.resolve()),
        "actor": args.actor,
        "code_revision": args.code_revision,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, indent=2))
        return 0
    if not args.code_revision.strip() or not args.actor.strip():
        parser.error("Execution requires actor and code revision")
    if not args.bronze_db.exists() and not args.initialize:
        parser.error("Use --initialize to create an explicitly dedicated Bronze DB")
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.bronze import BronzeEventStore, qualified_bronze_name
    from nse_quant.data_platform.bronze_import import parse_events
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
    from nse_quant.data_platform.manifests import ManifestStore

    args.bronze_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(args.bronze_db))
    try:
        store = BronzeEventStore(conn)
        if args.initialize:
            store.initialize()
        store.verify_target()
        ledger = AuditLedger(conn)
        ledger.initialize()
        ledger.register_contract(
            DatasetContract(
                name="bronze.event_variants",
                version="1",
                layer=Layer.BRONZE,
                write_policy=WritePolicy.APPEND_OBSERVATIONS,
                entity_keys=("capture_event_id", "envelope_hash"),
                required_columns=(
                    "capture_event_id",
                    "envelope_hash",
                    "received_at",
                    "recorded_at",
                    "source",
                    "payload_hash",
                ),
                owner="capture",
            )
        )
        manifests = ManifestStore(args.manifest_root)
        payload = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        manifests.put(payload)
        parent = ledger.plan_job(
            command_name="ingest.kite_segments@1",
            actor_id=args.actor,
            scope_ref="sha256:" + hashlib.sha256(payload).hexdigest(),
            code_revision=args.code_revision,
            config_hash=hashlib.sha256(b"verified-kite-segments-v1").hexdigest(),
        )
        receipts = []
        with ledger.execution(parent):
            frame = 0
            for segment in segments:
                with segment.path.open("rb") as handle:
                    raw = handle.read(8_388_609)
                if len(raw) > 8_388_608 or hashlib.sha256(raw).hexdigest() != segment.sha256:
                    raise ValueError("Segment changed after verification")
                events = parse_events(raw)
                if len(events) != segment.records:
                    raise ValueError("Segment envelope count changed")
                for event in events:
                    frame += 1
                    if (
                        event.capture_session_id != final["capture_session_id"]
                        or event.source_record_id != f"frame-{frame:012d}"
                        or event.source != "kite_websocket"
                        or event.origin_kind != "live_provider"
                    ):
                        raise ValueError("Captured identity/session mismatch")
                step_plan = json.dumps(
                    {
                        "session_id": final["capture_session_id"],
                        "segment": segment.path.name,
                        "sha256": segment.sha256,
                    },
                    sort_keys=True,
                ).encode()
                manifests.put(step_plan)
                child = ledger.plan_job(
                    command_name="ingest.kite_segment@1",
                    actor_id=args.actor,
                    scope_ref="sha256:" + hashlib.sha256(step_plan).hexdigest(),
                    code_revision=args.code_revision,
                    parent_job_id=parent,
                    config_hash=hashlib.sha256(b"verified-kite-segments-v1").hexdigest(),
                )
                with ledger.execution(child):
                    key = f"kite:{final['capture_session_id']}:{segment.path.name}:{segment.sha256}"
                    receipt = store.append_batch(
                        events,
                        batch_key=key,
                        input_artifact=raw,
                        job_id=child,
                    )
                    item = {"child_job_id": child, "receipt": asdict(receipt)}
                    receipts.append(item)
                    manifests.put(json.dumps(item, sort_keys=True).encode())
            table = qualified_bronze_name(conn, "event_variants")
            conflicting = conn.execute(
                f"SELECT count(*) FROM (SELECT capture_event_id FROM {table} "
                "WHERE source = 'kite_websocket' AND capture_session_id = ? "
                "GROUP BY capture_event_id HAVING count(*) > 1)",
                [final["capture_session_id"]],
            ).fetchone()
            if conflicting is None:
                raise RuntimeError("Conflict validation failed")
            status = (
                "COMMITTED_WITH_CONFLICTS"
                if conflicting[0]
                else ("DRAINED" if segments else "EMPTY_SESSION")
            )
            result = {
                "status": status,
                "session_id": final["capture_session_id"],
                "job_id": parent,
                "conflicting_id_count": conflicting[0],
                "receipts": receipts,
            }
            manifests.put(json.dumps(result, sort_keys=True).encode())
        print(json.dumps(result, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
