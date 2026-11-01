"""Audited offline import and pinned snapshot normalization, reconstructed FS2b1."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.instrument_reference import (
    MAX_ARTIFACT_BYTES,
    PARSER_VERSION,
    TokenResolution,
    fingerprint,
    parse_instruments,
    resolve_token,
    snapshot_json,
)

SOURCE = "kite_instruments_offline"
FORMAT = "kite_instruments_csv_utf8"


def object_name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _job(ledger: Any, command: str, scope: str, actor: str, revision: str) -> str:
    return ledger.plan_job(
        command_name=command,
        actor_id=actor,
        scope_ref="sha256:" + scope,
        code_revision=revision,
        config_hash=fingerprint([PARSER_VERSION]),
    )


def import_reference_artifact(
    conn: Any,
    raw: bytes,
    *,
    import_session_id: str,
    source_record_id: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> tuple[str, str, bool]:
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("ARTIFACT_BYTE_LIMIT")
    store, ledger = BronzeEventStore(conn), AuditLedger(conn)
    if initialize:
        store.initialize()
        ledger.initialize()
    store.verify_target()
    now = datetime.now(UTC)
    tentative = BronzeEvent(
        SOURCE, import_session_id, source_record_id, now, raw, FORMAT, "historical_import"
    )
    variants = conn.execute(
        f"SELECT received_at,payload_hash FROM {store.object_name('event_variants')} "
        "WHERE capture_event_id=? ORDER BY ingest_sequence",
        [tentative.capture_event_id],
    ).fetchall()
    if len(variants) > 1:
        raise ValueError("RECEIPT_CONFLICT_REQUIRES_REVIEW")
    received = variants[0][0] if variants and variants[0][1] == tentative.payload_hash else now
    event = BronzeEvent(
        SOURCE, import_session_id, source_record_id, received, raw, FORMAT, "historical_import"
    )
    scope = fingerprint([event.capture_event_id, event.envelope_hash, event.payload_hash])
    job = _job(ledger, "ingest.kite_instrument_artifact@1", scope, actor_id, code_revision)
    with ledger.execution(job):
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
        receipt = store.append_batch(
            (event,),
            batch_key="instrument-artifact:" + scope,
            input_artifact=raw,
            job_id=job,
            max_payload_bytes=MAX_ARTIFACT_BYTES,
        )
    return event.capture_event_id, event.envelope_hash, bool(receipt.conflict_variants)


def normalize_reference(
    bronze: Any,
    silver: Any,
    *,
    capture_event_id: str,
    envelope_hash: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> str:
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    bp = {r[2] for r in bronze.execute("PRAGMA database_list").fetchall() if r[2]}
    sp = {r[2] for r in silver.execute("PRAGMA database_list").fetchall() if r[2]}
    if bronze is silver or bp & sp:
        raise ValueError("SEPARATE_DATABASES_REQUIRED")
    source = object_name(bronze, "bronze", "event_variants")
    row = bronze.execute(
        f"SELECT payload,payload_hash,envelope_json,received_at,recorded_at,source,payload_format "
        f"FROM {source} WHERE capture_event_id=? AND envelope_hash=?",
        [capture_event_id, envelope_hash],
    ).fetchone()
    if row is None:
        raise ValueError("PINNED_BRONZE_VARIANT_NOT_FOUND")
    raw, payload_hash, envelope_json, received, recorded, provider, fmt = row
    raw = bytes(raw)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("ARTIFACT_BYTE_LIMIT")
    envelope = json.loads(envelope_json)
    if (
        hashlib.sha256(raw).hexdigest() != payload_hash
        or hashlib.sha256(envelope_json.encode()).hexdigest() != envelope_hash
        or fingerprint(
            [envelope["source"], envelope["capture_session_id"], envelope["source_record_id"]]
        )
        != capture_event_id
        or envelope.get("payload_hash") != payload_hash
        or envelope.get("source") != provider
        or envelope.get("payload_format") != fmt
        or datetime.fromisoformat(envelope["received_at"]) != received
    ):
        raise ValueError("BRONZE_INTEGRITY_FAILURE")
    if provider != SOURCE or fmt != FORMAT or envelope.get("origin_kind") != "historical_import":
        raise ValueError("UNSUPPORTED_REFERENCE_ORIGIN")
    if silver.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema NOT IN ('silver','medallion_audit')"
    ).fetchall():
        raise ValueError("DEDICATED_SILVER_REQUIRED")
    revision = fingerprint([capture_event_id, envelope_hash, payload_hash, PARSER_VERSION])
    ledger = AuditLedger(silver)
    if initialize:
        ledger.initialize()
    job = _job(ledger, "normalize.kite_instrument_reference@1", revision, actor_id, code_revision)
    target = object_name(silver, "silver", "instrument_reference_snapshots")
    with ledger.execution(job):
        if initialize:
            silver.execute(f"CREATE SCHEMA IF NOT EXISTS {target.rsplit('.', 1)[0]}")
            silver.execute(f"""CREATE TABLE IF NOT EXISTS {target} (
                revision_id VARCHAR PRIMARY KEY, schema_version INTEGER NOT NULL,
                source_observation_id VARCHAR NOT NULL, envelope_hash VARCHAR NOT NULL,
                payload_hash VARCHAR NOT NULL, parser_version VARCHAR NOT NULL,
                import_received_at TIMESTAMPTZ NOT NULL,
                bronze_recorded_at TIMESTAMPTZ NOT NULL, normalized_at TIMESTAMPTZ NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL,
                provider_received_at TIMESTAMPTZ, provider_published_at TIMESTAMPTZ,
                effective_from TIMESTAMPTZ, effective_to TIMESTAMPTZ, published_at TIMESTAMPTZ,
                classification VARCHAR NOT NULL, reason_code VARCHAR NOT NULL,
                record_count BIGINT NOT NULL, snapshot_json VARCHAR NOT NULL,
                first_job_id VARCHAR NOT NULL)""")
        ledger.register_contract(
            DatasetContract(
                name="silver.instrument_reference_snapshots",
                version="1",
                layer=Layer.SILVER,
                write_policy=WritePolicy.APPEND_REVISIONS,
                entity_keys=("revision_id",),
                required_columns=("revision_id", "source_observation_id", "recorded_at"),
                owner="instrument_reference",
            )
        )
        normalized_at = datetime.now(UTC)
        snapshot = parse_instruments(raw)
        encoded = snapshot_json(snapshot)
        silver.execute("BEGIN TRANSACTION")
        try:
            previous = silver.execute(
                f"SELECT snapshot_json,schema_version FROM {target} WHERE revision_id=?", [revision]
            ).fetchone()
            if previous is not None:
                if previous != (encoded, 1):
                    raise ValueError("REFERENCE_VERSION_CONTENT_MISMATCH")
            else:
                values = [
                    revision,
                    1,
                    capture_event_id,
                    envelope_hash,
                    payload_hash,
                    PARSER_VERSION,
                    received,
                    recorded,
                    normalized_at,
                    datetime.now(UTC),
                    None,
                    None,
                    None,
                    None,
                    None,
                    snapshot.classification,
                    snapshot.reason_code,
                    len(snapshot.records),
                    encoded,
                    job,
                ]
                placeholders = ",".join(["?"] * 20)
                silver.execute(f"INSERT INTO {target} VALUES ({placeholders})", values)
            silver.execute("COMMIT")
        except BaseException:
            silver.execute("ROLLBACK")
            raise
    return revision


def lookup_reference(
    bronze: Any,
    silver: Any,
    *,
    reference_revision_id: str,
    instrument_token: int,
) -> TokenResolution:
    target = object_name(silver, "silver", "instrument_reference_snapshots")
    row = silver.execute(
        f"SELECT source_observation_id,envelope_hash,payload_hash,parser_version,schema_version,"
        f"snapshot_json FROM {target} WHERE revision_id=?",
        [reference_revision_id],
    ).fetchone()
    if row is None:
        raise ValueError("PINNED_REFERENCE_NOT_FOUND")
    event, envelope_hash, payload_hash, parser, schema, encoded = row
    if parser != PARSER_VERSION or schema != 1:
        raise ValueError("UNSUPPORTED_REFERENCE_VERSION")
    if fingerprint([event, envelope_hash, payload_hash, parser]) != reference_revision_id:
        raise ValueError("REFERENCE_IDENTITY_MISMATCH")
    source = object_name(bronze, "bronze", "event_variants")
    original = bronze.execute(
        f"SELECT payload,envelope_json FROM {source} WHERE capture_event_id=? AND envelope_hash=?",
        [event, envelope_hash],
    ).fetchone()
    if original is None:
        raise ValueError("PINNED_BRONZE_VARIANT_NOT_FOUND")
    raw, envelope_json = bytes(original[0]), original[1]
    if (
        len(raw) > MAX_ARTIFACT_BYTES
        or hashlib.sha256(raw).hexdigest() != payload_hash
        or hashlib.sha256(envelope_json.encode()).hexdigest() != envelope_hash
    ):
        raise ValueError("BRONZE_INTEGRITY_FAILURE")
    envelope = json.loads(envelope_json)
    if (
        fingerprint(
            [envelope["source"], envelope["capture_session_id"], envelope["source_record_id"]]
        )
        != event
        or envelope.get("payload_hash") != payload_hash
        or envelope.get("source") != SOURCE
        or envelope.get("payload_format") != FORMAT
        or envelope.get("origin_kind") != "historical_import"
    ):
        raise ValueError("BRONZE_INTEGRITY_FAILURE")
    snapshot = parse_instruments(raw)
    if snapshot_json(snapshot) != encoded:
        raise ValueError("REFERENCE_VERSION_CONTENT_MISMATCH")
    return resolve_token(
        snapshot, reference_revision_id=reference_revision_id, instrument_token=instrument_token
    )
