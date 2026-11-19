"""Audited append-only normalization of one exact Bronze variant."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.kite_decoder import DECODER_VERSION, decode


def canonical(value: object) -> str:
    def timestamp(item: object) -> str:
        if isinstance(item, datetime):
            return item.astimezone(UTC).isoformat()
        raise TypeError("Unsupported canonical value")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=timestamp)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def name(conn: Any, schema: str, table: str) -> str:
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (catalog, schema, table))


def normalize_variant(
    bronze: Any,
    silver: Any,
    *,
    capture_event_id: str,
    envelope_hash: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> str:
    if bronze is silver or not actor_id.strip() or not code_revision.strip():
        raise ValueError("Separate connections and execution identities required")
    bp = {str(r[2]) for r in bronze.execute("PRAGMA database_list").fetchall() if r[2]}
    sp = {str(r[2]) for r in silver.execute("PRAGMA database_list").fetchall() if r[2]}
    if bp & sp:
        raise ValueError("SEPARATE_DATABASE_FILES_REQUIRED")
    table = name(bronze, "bronze", "event_variants")
    row = bronze.execute(
        f"SELECT payload,payload_hash,envelope_json,received_at,recorded_at,source,"
        f"payload_format FROM {table} WHERE capture_event_id=? AND envelope_hash=?",
        [capture_event_id, envelope_hash],
    ).fetchone()
    if row is None:
        raise ValueError("PINNED_BRONZE_VARIANT_NOT_FOUND")
    payload, ph, ej, received, recorded, source, fmt = row
    payload = bytes(payload)
    envelope = json.loads(ej)
    identity = [envelope["source"], envelope["capture_session_id"], envelope["source_record_id"]]
    if (
        digest(payload) != ph
        or digest(ej.encode()) != envelope_hash
        or digest(canonical(identity).encode()) != capture_event_id
        or envelope.get("payload_hash") != ph
        or envelope.get("source") != source
        or envelope.get("payload_format") != fmt
        or datetime.fromisoformat(envelope["received_at"]) != received
    ):
        raise ValueError("BRONZE_INTEGRITY_FAILURE")
    if source != "kite_websocket":
        raise ValueError("UNSUPPORTED_BRONZE_SOURCE")
    forbidden = silver.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema NOT IN ('silver','medallion_audit')"
    ).fetchall()
    if forbidden:
        raise ValueError("DEDICATED_SILVER_DATABASE_REQUIRED")
    target = name(silver, "silver", "kite_frames")
    versions_table = name(silver, "silver", "kite_schema_versions")
    ledger = AuditLedger(silver)
    if initialize:
        ledger.initialize()
    revision = digest(canonical([capture_event_id, envelope_hash, ph, DECODER_VERSION]).encode())
    job = ledger.plan_job(
        command_name="normalize.kite_binary@1",
        actor_id=actor_id,
        scope_ref="sha256:" + revision,
        code_revision=code_revision,
        config_hash=digest(DECODER_VERSION.encode()),
    )
    with ledger.execution(job):
        if initialize:
            schema = target.rsplit(".", 1)[0]
            silver.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            silver.execute(
                f"CREATE TABLE IF NOT EXISTS {versions_table} (version INTEGER PRIMARY KEY)"
            )
            versions = silver.execute(f"SELECT version FROM {versions_table}").fetchall()
            if versions and versions != [(1,)]:
                raise ValueError("UNSUPPORTED_SILVER_SCHEMA_VERSION")
            if not versions:
                silver.execute(f"INSERT INTO {versions_table} VALUES (1)")
            silver.execute(f"""CREATE TABLE IF NOT EXISTS {target} (
                revision_id VARCHAR PRIMARY KEY, source_observation_id VARCHAR NOT NULL,
                envelope_hash VARCHAR NOT NULL, payload_hash VARCHAR NOT NULL,
                decoder_version VARCHAR NOT NULL, received_at TIMESTAMPTZ NOT NULL,
                bronze_recorded_at TIMESTAMPTZ NOT NULL, normalized_at TIMESTAMPTZ NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL, published_at TIMESTAMPTZ,
                classification VARCHAR NOT NULL, reason_code VARCHAR NOT NULL,
                result_json VARCHAR NOT NULL, job_id VARCHAR NOT NULL)""")
        if silver.execute(f"SELECT version FROM {versions_table}").fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_SILVER_SCHEMA_VERSION")
        from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

        ledger.register_contract(
            DatasetContract(
                name="silver.kite_frames",
                version="1",
                layer=Layer.SILVER,
                write_policy=WritePolicy.APPEND_REVISIONS,
                entity_keys=("revision_id",),
                required_columns=("revision_id", "source_observation_id", "recorded_at"),
                owner="native_kite_normalization",
            )
        )
        normalized = datetime.now(UTC)
        result = decode(payload, fmt)
        encoded = canonical(asdict(result))
        silver.execute("BEGIN TRANSACTION")
        try:
            previous = silver.execute(
                f"SELECT result_json FROM {target} WHERE revision_id=?", [revision]
            ).fetchone()
            if previous is not None:
                if previous[0] != encoded:
                    raise ValueError("DECODER_VERSION_CONTENT_MISMATCH")
            else:
                silver.execute(
                    f"INSERT INTO {target} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        revision,
                        capture_event_id,
                        envelope_hash,
                        ph,
                        DECODER_VERSION,
                        received,
                        recorded,
                        normalized,
                        datetime.now(UTC),
                        None,
                        result.classification,
                        result.reason_code,
                        encoded,
                        job,
                    ],
                )
            silver.execute("COMMIT")
        except BaseException:
            silver.execute("ROLLBACK")
            raise
    return revision
