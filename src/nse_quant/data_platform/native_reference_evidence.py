"""Bounded, transaction-consistent verification of an explicitly pinned HTTP pair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.native_reference_decode import canonical, digest

SOURCE = "kite_instruments_http"
CAPTURE_VERSION = "kite-instrument-http@2"


def object_name(conn: Any, schema: str, name: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(s).replace('"', '""') + '"' for s in (row[0], schema, name))


def instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GateRejected("INVALID_RECEIPT_TIME")
    return value.astimezone(UTC).isoformat()


def strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise GateRejected("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise GateRejected("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


class GateRejected(ValueError):
    pass


@dataclass(frozen=True)
class ReferencePins:
    body_capture_event_id: str
    body_envelope_hash: str
    metadata_capture_event_id: str
    metadata_envelope_hash: str

    def __post_init__(self) -> None:
        for value in (
            self.body_capture_event_id,
            self.body_envelope_hash,
            self.metadata_capture_event_id,
            self.metadata_envelope_hash,
        ):
            if not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValueError("EXACT_SHA256_PINS_REQUIRED")


@dataclass(frozen=True)
class PairEvidence:
    gate_code: str
    evidence_json: str
    source_times_json: str
    body_payload_hash: str | None
    metadata_payload_hash: str | None
    raw_body: bytes = field(repr=False)
    headers: tuple[tuple[str, str], ...] = ()

    @property
    def gate_fingerprint(self) -> str:
        return digest(self.evidence_json.encode())


def inspect_reference_pair(conn: Any, pins: ReferencePins) -> PairEvidence:
    """Caller owns a read-only connection, without an external transaction."""
    table = object_name(conn, "bronze", "event_variants")
    evidence: dict[str, Any] = {"gate_version": 1}
    times: dict[str, str | None] = {}
    body: dict[str, Any] | None = None
    metadata_row: dict[str, Any] | None = None
    raw = b""
    headers: tuple[tuple[str, str], ...] = ()
    code = "VERIFIED"
    conn.execute("BEGIN TRANSACTION")
    try:

        def read(event: str, envelope: str, label: str, limit: int) -> dict[str, Any]:
            variants = conn.execute(
                f"SELECT envelope_hash FROM {table} WHERE capture_event_id=? "
                "ORDER BY envelope_hash LIMIT 33",
                [event],
            ).fetchall()
            evidence[label + "_variants"] = [v[0] for v in variants]
            evidence[label + "_variant_limit_reached"] = len(variants) == 33
            if len(variants) > 1:
                raise GateRejected("RECEIPT_CONFLICT")
            row = conn.execute(
                f"SELECT capture_event_id,envelope_hash,source,capture_session_id,source_record_id,"
                f"received_at,recorded_at,payload_hash,payload_format,origin_kind,"
                f"first_batch_key,first_job_id,"
                f"CASE WHEN octet_length(payload)<=? THEN payload ELSE NULL END,"
                f"CASE WHEN length(envelope_json)<=32768 THEN envelope_json ELSE NULL END "
                f"FROM {table} WHERE capture_event_id=? AND envelope_hash=?",
                [limit, event, envelope],
            ).fetchone()
            if row is None:
                raise GateRejected("PINNED_VARIANT_NOT_FOUND")
            keys = (
                "id",
                "envelope",
                "source",
                "session",
                "record",
                "received",
                "recorded",
                "hash",
                "format",
                "origin",
                "batch",
                "job",
                "payload",
                "envelope_json",
            )
            value = dict(zip(keys, row, strict=True))
            evidence[label + "_lineage"] = [
                value[k] for k in ("id", "envelope", "hash", "batch", "job")
            ]
            if value["payload"] is None or value["envelope_json"] is None:
                raise GateRejected("BRONZE_RESOURCE_LIMIT")
            payload = bytes(value["payload"])
            envelope_value = strict_json(value["envelope_json"])
            required = {
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
            if (
                set(envelope_value) != required
                or envelope_value["envelope_version"] != 1
                or type(envelope_value["envelope_version"]) is not int
                or canonical(envelope_value) != value["envelope_json"]
                or digest(value["envelope_json"].encode()) != envelope
                or digest(
                    canonical(
                        [
                            envelope_value["source"],
                            envelope_value["capture_session_id"],
                            envelope_value["source_record_id"],
                        ]
                    ).encode()
                )
                != event
                or digest(payload) != value["hash"]
                or envelope_value["payload_hash"] != value["hash"]
                or envelope_value["source"] != value["source"]
                or envelope_value["capture_session_id"] != value["session"]
                or envelope_value["source_record_id"] != value["record"]
                or envelope_value["payload_format"] != value["format"]
                or envelope_value["origin_kind"] != value["origin"]
                or instant(datetime.fromisoformat(envelope_value["received_at"]))
                != instant(value["received"])
                or any(
                    envelope_value[k] is not None
                    for k in ("exchange_ts", "provider_event_id", "instrument_ref")
                )
            ):
                raise GateRejected("BRONZE_INTEGRITY_FAILURE")
            value["payload"] = payload
            times[label + "_received_at"] = instant(value["received"])
            times[label + "_recorded_at"] = instant(value["recorded"])
            return value

        body = read(pins.body_capture_event_id, pins.body_envelope_hash, "body", 8_388_609)
        metadata_row = read(
            pins.metadata_capture_event_id, pins.metadata_envelope_hash, "metadata", 32768
        )
        if (
            body["source"] != SOURCE
            or metadata_row["source"] != SOURCE
            or body["origin"] != "live_provider"
            or metadata_row["origin"] != "live_provider"
            or body["record"] != "response-body"
            or metadata_row["record"] != "response-metadata"
            or body["session"] != metadata_row["session"]
            or body["batch"] != metadata_row["batch"]
            or body["job"] != metadata_row["job"]
        ):
            raise GateRejected("HTTP_PAIR_LINEAGE_MISMATCH")
        batches = object_name(conn, "bronze", "ingest_batches")
        batch = conn.execute(
            f"SELECT batch_fingerprint,input_file_hash,input_events,conflict_variants,job_id "
            f"FROM {batches} WHERE batch_key=?",
            [body["batch"]],
        ).fetchone()
        evidence["batch"] = list(batch) if batch else None
        expected_batch = digest(
            canonical(
                {
                    "input_file_hash": body["hash"],
                    "events": [
                        [body["id"], body["envelope"]],
                        [metadata_row["id"], metadata_row["envelope"]],
                    ],
                }
            ).encode()
        )
        if batch != (expected_batch, body["hash"], 2, 0, body["job"]):
            raise GateRejected("HTTP_BATCH_NOT_VERIFIED")
        artifacts = object_name(conn, "bronze", "input_artifacts")
        artifact = conn.execute(
            f"SELECT CASE WHEN octet_length(artifact_bytes)<=8388609 THEN artifact_bytes "
            f"ELSE NULL END FROM {artifacts} WHERE artifact_hash=?",
            [body["hash"]],
        ).fetchone()
        if artifact is None or artifact[0] is None or bytes(artifact[0]) != body["payload"]:
            raise GateRejected("HTTP_ARTIFACT_NOT_VERIFIED")
        evidence["artifact_hash"] = body["hash"]
        jobs = object_name(conn, "medallion_audit", "jobs")
        events = object_name(conn, "medallion_audit", "job_events")
        job = conn.execute(
            f"SELECT command_name,scope_ref,config_hash FROM {jobs} WHERE job_id=?", [body["job"]]
        ).fetchone()
        state = conn.execute(
            f"SELECT event_index,state FROM {events} WHERE job_id=? "
            "ORDER BY event_index DESC LIMIT 1",
            [body["job"]],
        ).fetchone()
        evidence["acquisition_job"] = [
            body["job"],
            list(job) if job else None,
            list(state) if state else None,
        ]
        if job is None or job[0] != "ingest.kite_instruments_http@1" or state is None:
            raise GateRejected("ACQUISITION_AUDIT_MISSING")
        if state[1] != "SUCCEEDED":
            raise GateRejected("ACQUISITION_NOT_SUCCEEDED")
        metadata = strict_json(metadata_row["payload"].decode("utf-8"))
        if (
            type(metadata.get("metadata_schema_version")) is not int
            or metadata["metadata_schema_version"] != 1
            or metadata.get("capture_version") != CAPTURE_VERSION
        ):
            raise GateRejected("UNSUPPORTED_CAPTURE_VERSION")
        if (
            metadata.get("body_capture_event_id") != body["id"]
            or metadata.get("body_envelope_hash") != body["envelope"]
            or metadata.get("body_payload_hash") != body["hash"]
            or metadata.get("captured_body_hash") != body["hash"]
            or metadata.get("capture_session_id") != body["session"]
            or type(metadata.get("body_bytes")) is not int
            or metadata["body_bytes"] != len(body["payload"])
        ):
            raise GateRejected("HTTP_METADATA_LINK_MISMATCH")
        if (
            metadata.get("host") != "api.kite.trade"
            or metadata.get("method") != "GET"
            or not isinstance(metadata.get("path"), str)
            or not re.fullmatch(r"/instruments(?:/[A-Z]{2,8})?", metadata["path"])
        ):
            raise GateRejected("UNSUPPORTED_HTTP_ENDPOINT")
        scope = digest(canonical([SOURCE, body["session"]]).encode())
        policy = metadata["policy"]
        policy_keys = {
            "max_body_bytes",
            "chunk_bytes",
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "elapsed_budget_seconds",
        }
        if not isinstance(policy, dict) or set(policy) != policy_keys:
            raise GateRejected("UNSUPPORTED_CAPTURE_POLICY")
        for key, cap in (("max_body_bytes", 8_388_608), ("chunk_bytes", 65_536)):
            if type(policy[key]) is not int or not 1 <= policy[key] <= cap:
                raise GateRejected("UNSUPPORTED_CAPTURE_POLICY")
        for key in ("connect_timeout_seconds", "read_timeout_seconds", "elapsed_budget_seconds"):
            if type(policy[key]) not in (int, float) or not 0 < policy[key] <= 120:
                raise GateRejected("UNSUPPORTED_CAPTURE_POLICY")
        config = digest(canonical([CAPTURE_VERSION, metadata["path"], metadata["policy"]]).encode())
        if job[1:] != ("sha256:" + scope, config):
            raise GateRejected("ACQUISITION_CONFIG_MISMATCH")
        if (
            body["format"] != "http_entity_body_content_coded"
            or metadata_row["format"] != "kite_instrument_http_metadata_json@1"
            or type(metadata.get("status_code")) is not int
            or metadata["status_code"] != 200
            or any(
                metadata.get(k) is not True
                for k in (
                    "headers_complete",
                    "body_complete",
                    "body_observed",
                    "transport_accepted",
                )
            )
            or metadata.get("payload_is_incomplete") is not False
            or type(metadata.get("returned_bytes_not_retained")) is not int
            or metadata["returned_bytes_not_retained"] != 0
            or metadata.get("reason_code") != "COMPLETE"
            or metadata.get("disposition_code") != "UNVALIDATED_HTTP_CAPTURE"
            or metadata.get("csv_validated") is not False
            or not body["payload"]
            or metadata.get("body_representation") != "HTTP_ENTITY_BODY_CONTENT_CODING_PRESERVED"
            or metadata.get("header_scope") != "SELECTED_ALLOWLIST_ONLY_NOT_RAW_HEADERS"
        ):
            raise GateRejected("HTTP_RESPONSE_NOT_COMPLETE")
        if any(metadata[k] is not None for k in ("provider_published_at", "platform_published_at")):
            raise GateRejected("UNSUPPORTED_PUBLICATION_METADATA")
        if (
            metadata.get("receipt_time_semantics")
            != "LOCAL_CAPTURE_END_NOT_EXCHANGE_OR_PUBLICATION"
        ):
            raise GateRejected("UNSUPPORTED_RECEIPT_SEMANTICS")
        for key in (
            "request_started_at",
            "headers_received_at",
            "first_chunk_returned_at",
            "capture_finished_at",
        ):
            times[key] = instant(datetime.fromisoformat(metadata[key]))
        if times["capture_finished_at"] != times["body_received_at"] or (
            times["metadata_received_at"] != times["body_received_at"]
        ):
            raise GateRejected("RECEIPT_TIME_MISMATCH")
        selected = metadata["selected_headers"]
        if not isinstance(selected, list) or len(selected) > 32:
            raise GateRejected("INVALID_SELECTED_HEADERS")
        if any(
            not isinstance(p, list)
            or len(p) != 2
            or any(not isinstance(v, str) or len(v) > 2048 for v in p)
            for p in selected
        ):
            raise GateRejected("INVALID_SELECTED_HEADERS")
        allowed = {
            "content-type",
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "date",
            "last-modified",
            "etag",
            "cache-control",
            "expires",
            "vary",
        }
        headers = tuple((p[0], p[1]) for p in selected)
        if (
            any(k not in allowed for k, _ in headers)
            or sum(len(json.dumps(pair, ensure_ascii=True)) for pair in headers) > 16384
        ):
            raise GateRejected("INVALID_SELECTED_HEADERS")
        lengths = [v for k, v in headers if k == "content-length"]
        transfers = [v for k, v in headers if k == "transfer-encoding"]
        if (
            len(lengths) > 1
            or len(transfers) > 1
            or (lengths and transfers)
            or (transfers and transfers[0].lower() != "chunked")
            or (
                lengths
                and (
                    not re.fullmatch(r"[0-9]{1,20}", lengths[0].strip())
                    or int(lengths[0]) != len(body["payload"])
                )
            )
        ):
            raise GateRejected("HTTP_FRAMING_NOT_VERIFIED")
        if len(body["payload"]) > metadata["policy"]["max_body_bytes"]:
            raise GateRejected("CAPTURE_POLICY_LIMIT_EXCEEDED")
        raw = body["payload"]
    except GateRejected as error:
        code = str(error)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        code = "MALFORMED_RECEIPT_EVIDENCE"
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    evidence["gate_code"] = code
    return PairEvidence(
        code,
        canonical(evidence),
        canonical(times),
        body["hash"] if body else None,
        metadata_row["hash"] if metadata_row else None,
        raw if code == "VERIFIED" else b"",
        headers if code == "VERIFIED" else (),
    )
