"""Bounded JSONL envelope import; original artifact and payload bytes are preserved."""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import duckdb

from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore, sha256


def parse_events(raw: bytes) -> tuple[BronzeEvent, ...]:
    if len(raw) > 16_777_216:
        raise ValueError("Input exceeds 16 MiB")
    events = []
    required = {
        "envelope_version",
        "source",
        "capture_session_id",
        "source_record_id",
        "received_at",
        "payload_base64",
        "payload_format",
        "origin_kind",
    }
    optional = {"exchange_ts", "provider_event_id", "instrument_ref"}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError("Incomplete event envelope")
        if set(item) - required - optional or type(item["envelope_version"]) is not int:
            raise ValueError("Unknown envelope fields or invalid version")
        if item["envelope_version"] != 1:
            raise ValueError("Unsupported event envelope version")
        for key in required - {"envelope_version"}:
            if not isinstance(item[key], str):
                raise ValueError("Envelope fields must use declared string types")
        for key in optional:
            if item.get(key) is not None and not isinstance(item[key], str):
                raise ValueError("Optional envelope fields must be strings or null")
        event = BronzeEvent(
            source=item["source"],
            capture_session_id=item["capture_session_id"],
            source_record_id=item["source_record_id"],
            received_at=datetime.fromisoformat(item["received_at"]),
            payload=base64.b64decode(item["payload_base64"], validate=True),
            payload_format=item["payload_format"],
            origin_kind=item["origin_kind"],
            exchange_ts=(
                datetime.fromisoformat(item["exchange_ts"]) if item.get("exchange_ts") else None
            ),
            provider_event_id=item.get("provider_event_id"),
            instrument_ref=item.get("instrument_ref"),
        )
        if len(event.payload) > 1_048_576:
            raise ValueError("Payload exceeds 1 MiB")
        events.append(event)
        if len(events) > 10_000:
            raise ValueError("Input exceeds 10,000 events")
    if not events:
        raise ValueError("No event envelopes found")
    return tuple(events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    with args.input.open("rb") as handle:
        raw = handle.read(16_777_217)
    events = parse_events(raw)
    if args.input.resolve() == args.bronze_db.resolve():
        parser.error("Input artifact and target database must be different files")
    plan = {
        "kind": "bronze_event_import",
        "version": 1,
        "input_hash": sha256(raw),
        "batch_key": args.batch_key,
        "events": len(events),
        "sources": sorted({event.source for event in events}),
        "capture_sessions": sorted({event.capture_session_id for event in events}),
        "target_db": str(args.bronze_db.resolve()),
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, indent=2))
        return 0
    if not all(value.strip() for value in (args.batch_key, args.actor, args.code_revision)):
        parser.error("Execution requires batch key, actor and code revision")
    if not args.bronze_db.exists() and not args.initialize:
        parser.error("Target DB must exist; use explicit --initialize for a dedicated new DB")
    from nse_quant.data_platform.audit import AuditLedger
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
        job = ledger.plan_job(
            command_name="ingest.bronze_events@1",
            actor_id=args.actor,
            scope_ref="sha256:" + sha256(payload),
            code_revision=args.code_revision,
            config_hash=sha256(b"bronze-envelope-v1;10000-events;1MiB-payload;16MiB-artifact"),
        )
        with ledger.execution(job):
            receipt = store.append_batch(
                events,
                batch_key=args.batch_key,
                input_artifact=raw,
                job_id=job,
            )
            conflicts = set(store.conflicting_event_ids())
            affected = sorted({event.capture_event_id for event in events} & conflicts)
            summary = {
                "job_id": job,
                "plan_hash": sha256(payload),
                "receipt": asdict(receipt),
                "status": "COMMITTED_WITH_CONFLICTS" if affected else "COMMITTED",
                "conflicting_capture_ids": affected,
            }
            manifests.put(json.dumps(summary, sort_keys=True, separators=(",", ":")).encode())
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
