"""Read-only, source-recomputed evidence for one explicitly pinned Silver frame."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.kite_decoder import DECODER_VERSION, DecodedFrame, decode

READER_VERSION = "kite-frame-consumer@1"
MAX_PAYLOAD_BYTES = 1_048_576
MAX_RESULT_BYTES = 16_777_216
MAX_ENVELOPE_BYTES = 32_768


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _canonical(value: object) -> str:
    def timestamp(item: object) -> str:
        if not isinstance(item, datetime) or item.tzinfo is None or item.utcoffset() is None:
            raise ValueError("AWARE_TIME_REQUIRED")
        return item.astimezone(UTC).isoformat()

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=timestamp, allow_nan=False
    )


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class KiteFrameEvidence:
    reader_version: str
    revision_id: str
    status: str
    reason_code: str
    source_observation_id: str | None = None
    envelope_hash: str | None = None
    payload_hash: str | None = None
    decoder_version: str | None = None
    received_at: str | None = None
    bronze_recorded_at: str | None = None
    evidence_fingerprint: str | None = None
    decoded: DecodedFrame | None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_kite_frame(
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
) -> KiteFrameEvidence:
    """Caller owns separate read-only connections, neither in a transaction.

    Each database is read in its own transaction. This is NOT a cross-database
    snapshot, a durable evidence manifest or a publication/decision barrier.
    Non-quote dispositions can be verified, but are never salvaged into quotes.
    SQL/connection failures propagate; expected evidence failures return blocked.
    """
    if not _valid_hash(revision_id):
        raise ValueError("EXACT_FRAME_REVISION_REQUIRED")
    bp = {r[2] for r in bronze.execute("PRAGMA database_list").fetchall() if r[2]}
    sp = {r[2] for r in silver.execute("PRAGMA database_list").fetchall() if r[2]}
    if bronze is silver or bp & sp:
        raise ValueError("SEPARATE_DATABASES_REQUIRED")

    def blocked(reason: str) -> KiteFrameEvidence:
        return KiteFrameEvidence(READER_VERSION, revision_id, "blocked", reason)

    frames = _name(silver, "silver", "kite_frames")
    versions = _name(silver, "silver", "kite_schema_versions")
    jobs = _name(silver, "medallion_audit", "jobs")
    events = _name(silver, "medallion_audit", "job_events")
    silver.execute("BEGIN TRANSACTION")
    try:
        schema = silver.execute(f"SELECT version FROM {versions} LIMIT 2").fetchall()
        row = silver.execute(
            f"SELECT source_observation_id,envelope_hash,payload_hash,decoder_version,"
            f"received_at,bronze_recorded_at,classification,reason_code,"
            f"CASE WHEN octet_length(encode(result_json))<=? THEN result_json ELSE NULL END,"
            f"job_id FROM {frames} WHERE revision_id=?",
            [MAX_RESULT_BYTES, revision_id],
        ).fetchone()
        job = state = None
        if row is not None:
            job = silver.execute(
                f"SELECT command_name,scope_ref,config_hash FROM {jobs} WHERE job_id=?",
                [row[9]],
            ).fetchone()
            state = silver.execute(
                f"SELECT state FROM {events} WHERE job_id=? ORDER BY event_index DESC LIMIT 1",
                [row[9]],
            ).fetchone()
        silver.execute("COMMIT")
    except BaseException:
        silver.execute("ROLLBACK")
        raise
    if schema != [(1,)]:
        return blocked("UNSUPPORTED_FRAME_SCHEMA")
    if row is None:
        return blocked("FRAME_NOT_FOUND")
    event_id, envelope_hash, payload_hash, decoder_version = row[:4]
    if not all(_valid_hash(v) for v in (event_id, envelope_hash, payload_hash)):
        return blocked("INVALID_FRAME_SOURCE_PINS")
    if decoder_version != DECODER_VERSION:
        return blocked("UNSUPPORTED_FRAME_DECODER")
    if _hash([event_id, envelope_hash, payload_hash, decoder_version]) != revision_id:
        return blocked("FRAME_REVISION_MISMATCH")
    if job != (
        "normalize.kite_binary@1",
        "sha256:" + revision_id,
        hashlib.sha256(DECODER_VERSION.encode()).hexdigest(),
    ) or state != ("SUCCEEDED",):
        return blocked("NORMALIZATION_AUDIT_NOT_VERIFIED")
    if row[8] is None:
        return blocked("FRAME_RESULT_LIMIT")
    table = _name(bronze, "bronze", "event_variants")
    bronze.execute("BEGIN TRANSACTION")
    try:
        variants = bronze.execute(
            f"SELECT envelope_hash FROM {table} WHERE capture_event_id=? "
            "ORDER BY envelope_hash LIMIT 2",
            [event_id],
        ).fetchall()
        source = bronze.execute(
            f"SELECT CASE WHEN octet_length(payload)<=? THEN payload ELSE NULL END,"
            f"payload_hash,CASE WHEN octet_length(encode(envelope_json))<=? "
            f"THEN envelope_json ELSE NULL END,received_at,recorded_at,source,payload_format,"
            f"capture_session_id,source_record_id,origin_kind "
            f"FROM {table} WHERE capture_event_id=? AND envelope_hash=?",
            [MAX_PAYLOAD_BYTES, MAX_ENVELOPE_BYTES, event_id, envelope_hash],
        ).fetchone()
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    if len(variants) > 1:
        return blocked("BRONZE_RECEIPT_CONFLICT")
    if source is None:
        return blocked("PINNED_BRONZE_VARIANT_NOT_FOUND")
    if source[0] is None or source[2] is None:
        return blocked("BRONZE_RESOURCE_LIMIT")
    try:
        payload = bytes(source[0])
        envelope = _strict_json(source[2])
        keys = {
            "envelope_version",
            "source",
            "capture_session_id",
            "source_record_id",
            "received_at",
            "payload_hash",
            "payload_format",
            "origin_kind",
            "exchange_ts",
            "provider_event_id",
            "instrument_ref",
        }
        if not isinstance(envelope, dict) or set(envelope) != keys:
            return blocked("BRONZE_ENVELOPE_CONTRACT_MISMATCH")
        if (
            type(envelope["envelope_version"]) is not int
            or envelope["envelope_version"] != 1
            or _canonical(envelope) != source[2]
            or hashlib.sha256(source[2].encode()).hexdigest() != envelope_hash
            or hashlib.sha256(payload).hexdigest() != payload_hash
            or source[1] != payload_hash
            or envelope["payload_hash"] != payload_hash
            or _hash(
                [envelope["source"], envelope["capture_session_id"], envelope["source_record_id"]]
            )
            != event_id
            or [
                envelope[k]
                for k in (
                    "source",
                    "payload_format",
                    "capture_session_id",
                    "source_record_id",
                    "origin_kind",
                )
            ]
            != list(source[5:10])
        ):
            return blocked("BRONZE_INTEGRITY_FAILURE")
        if source[5] != "kite_websocket" or source[9] != "live_provider":
            return blocked("UNSUPPORTED_FRAME_SOURCE")
        received = _instant(source[3])
        recorded = _instant(source[4])
        if (
            _instant(datetime.fromisoformat(envelope["received_at"])) != received
            or _instant(row[4]) != received
            or _instant(row[5]) != recorded
        ):
            return blocked("FRAME_SOURCE_TIME_MISMATCH")
        decoded = decode(payload, source[6])
        encoded = _canonical(asdict(decoded))
        if (row[6], row[7], row[8]) != (decoded.classification, decoded.reason_code, encoded):
            return blocked("FRAME_DECODE_CONTENT_MISMATCH")
        fingerprint = _hash(
            [
                READER_VERSION,
                revision_id,
                event_id,
                envelope_hash,
                payload_hash,
                decoder_version,
                received,
                recorded,
                encoded,
                row[9],
                list(job or ()),
                list(state or ()),
            ]
        )
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return blocked("MALFORMED_FRAME_EVIDENCE")
    return KiteFrameEvidence(
        READER_VERSION,
        revision_id,
        "verified",
        "SOURCE_RECOMPUTED",
        event_id,
        envelope_hash,
        payload_hash,
        decoder_version,
        received,
        recorded,
        fingerprint,
        decoded,
    )
