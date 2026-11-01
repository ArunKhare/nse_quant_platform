"""Append-only assessments of native HTTP receipts, never a publication API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.native_reference_decode import (
    CSV_VERSION,
    DECODER_VERSION,
    NativeReferenceResult,
    canonical,
    digest,
    normalize_native_content,
)
from nse_quant.data_platform.native_reference_evidence import (
    ReferencePins,
    inspect_reference_pair,
    object_name,
)

NORMALIZER_VERSION = "kite-native-http-reference@1"


def normalize_http_reference(
    bronze: Any,
    silver: Any,
    *,
    pins: ReferencePins,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    bp = {r[2] for r in bronze.execute("PRAGMA database_list").fetchall() if r[2]}
    sp = {r[2] for r in silver.execute("PRAGMA database_list").fetchall() if r[2]}
    if bronze is silver or bp & sp:
        raise ValueError("SEPARATE_DATABASES_REQUIRED")
    if silver.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema NOT IN ('silver','medallion_audit') LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_SILVER_REQUIRED")
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    ledger = AuditLedger(silver)
    if initialize:
        ledger.initialize()
    versions = [NORMALIZER_VERSION, DECODER_VERSION, CSV_VERSION]
    input_revision = digest(canonical([asdict(pins), versions]).encode())
    job = ledger.plan_job(
        command_name="normalize.kite_native_reference@1",
        actor_id=actor_id,
        scope_ref="sha256:" + input_revision,
        code_revision=code_revision,
        config_hash=digest(canonical(versions).encode()),
    )
    target = object_name(silver, "silver", "kite_http_reference_results")
    with ledger.execution(job):
        if initialize:
            silver.execute(f"CREATE SCHEMA IF NOT EXISTS {target.rsplit('.', 1)[0]}")
            silver.execute(f"""CREATE TABLE IF NOT EXISTS {target} (
                revision_id VARCHAR PRIMARY KEY, input_revision_id VARCHAR NOT NULL,
                schema_version INTEGER NOT NULL, source_observation_id VARCHAR NOT NULL,
                body_envelope_hash VARCHAR NOT NULL, body_payload_hash VARCHAR,
                metadata_capture_event_id VARCHAR NOT NULL, metadata_envelope_hash VARCHAR NOT NULL,
                metadata_payload_hash VARCHAR, normalizer_version VARCHAR NOT NULL,
                content_decoder_version VARCHAR NOT NULL, csv_version VARCHAR NOT NULL,
                gate_fingerprint VARCHAR NOT NULL, gate_evidence_json VARCHAR NOT NULL,
                source_times_json VARCHAR NOT NULL, normalized_at TIMESTAMPTZ NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL, published_at TIMESTAMPTZ,
                provider_published_at TIMESTAMPTZ, effective_from TIMESTAMPTZ,
                effective_to TIMESTAMPTZ, classification VARCHAR NOT NULL,
                reason_code VARCHAR NOT NULL, record_count BIGINT NOT NULL,
                result_json VARCHAR NOT NULL, supersedes_json VARCHAR NOT NULL,
                first_job_id VARCHAR NOT NULL)""")
        if silver.execute(f"SELECT 1 FROM {target} WHERE schema_version<>1 LIMIT 1").fetchone():
            raise ValueError("UNSUPPORTED_NATIVE_REFERENCE_SCHEMA")
        ledger.register_contract(
            DatasetContract(
                name="silver.kite_http_reference_results",
                version="1",
                layer=Layer.SILVER,
                write_policy=WritePolicy.APPEND_REVISIONS,
                entity_keys=("revision_id",),
                required_columns=("revision_id", "source_observation_id", "recorded_at"),
                owner="native_instrument_reference",
            )
        )
        evidence = inspect_reference_pair(bronze, pins)
        normalized_at = datetime.now(UTC)
        result = (
            normalize_native_content(evidence.raw_body, evidence.headers)
            if evidence.gate_code == "VERIFIED"
            else NativeReferenceResult("quarantine", evidence.gate_code)
        )
        encoded = canonical(asdict(result))
        revision = digest(canonical([input_revision, evidence.gate_fingerprint]).encode())
        silver.execute("BEGIN TRANSACTION")
        try:
            previous = silver.execute(
                f"SELECT result_json,gate_evidence_json,source_times_json,schema_version "
                f"FROM {target} WHERE revision_id=?",
                [revision],
            ).fetchone()
            if previous is not None:
                if previous != (encoded, evidence.evidence_json, evidence.source_times_json, 1):
                    raise ValueError("NORMALIZER_VERSION_CONTENT_MISMATCH")
                inserted = False
            else:
                prior = silver.execute(
                    f"SELECT revision_id FROM {target} WHERE input_revision_id=? "
                    "ORDER BY revision_id LIMIT 1001",
                    [input_revision],
                ).fetchall()
                if len(prior) > 1000:
                    raise ValueError("ASSESSMENT_HISTORY_LIMIT")
                supersedes = canonical([p[0] for p in prior])
                values = [
                    revision,
                    input_revision,
                    1,
                    pins.body_capture_event_id,
                    pins.body_envelope_hash,
                    evidence.body_payload_hash,
                    pins.metadata_capture_event_id,
                    pins.metadata_envelope_hash,
                    evidence.metadata_payload_hash,
                    *versions,
                    evidence.gate_fingerprint,
                    evidence.evidence_json,
                    evidence.source_times_json,
                    normalized_at,
                    datetime.now(UTC),
                    None,
                    None,
                    None,
                    None,
                    result.classification,
                    result.reason_code,
                    len(result.rows),
                    encoded,
                    supersedes,
                    job,
                ]
                placeholders = ",".join(["?"] * 27)
                silver.execute(f"INSERT INTO {target} VALUES ({placeholders})", values)
                inserted = True
            silver.execute("COMMIT")
        except BaseException:
            silver.execute("ROLLBACK")
            raise
    return {
        "revision_id": revision,
        "input_revision_id": input_revision,
        "job_id": job,
        "classification": result.classification,
        "reason_code": result.reason_code,
        "record_count": len(result.rows),
        "inserted": inserted,
        "published": False,
    }
