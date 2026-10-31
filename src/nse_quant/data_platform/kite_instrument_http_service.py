"""Audited HTTP-to-Bronze acquisition; no implicit Silver conversion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.kite_instrument_http import (
    CAPTURE_VERSION,
    DEFAULT_HTTP_POLICY,
    HttpCapture,
    HttpPolicy,
    KiteHttpCredentials,
    fetch_instrument_response,
    request_path,
)

SOURCE = "kite_instruments_http"
COMMAND = "ingest.kite_instruments_http@1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class HttpAcquisitionResult:
    job_id: str
    capture_session_id: str
    status: str
    reason_code: str
    body_capture_event_id: str
    body_envelope_hash: str
    metadata_capture_event_id: str
    metadata_envelope_hash: str


class HttpAcquisitionRejected(RuntimeError):
    def __init__(self, result: HttpAcquisitionResult) -> None:
        super().__init__(result.reason_code)
        self.result = result


def acquire_instrument_reference(
    conn: Any,
    credentials: KiteHttpCredentials,
    *,
    capture_session_id: str,
    actor_id: str,
    code_revision: str,
    exchange: str | None = None,
    initialize: bool = False,
    policy: HttpPolicy = DEFAULT_HTTP_POLICY,
    fetcher: Callable[..., HttpCapture] = fetch_instrument_response,
) -> HttpAcquisitionResult:
    """An attempted session cannot issue a second request, including after failure."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", capture_session_id):
        raise ValueError("INVALID_CAPTURE_SESSION")
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    path = request_path(exchange)
    store = BronzeEventStore(conn)
    ledger = AuditLedger(conn)
    if initialize:
        store.initialize()
        ledger.initialize()
    store.verify_target()
    scope = fingerprint([SOURCE, capture_session_id])
    attempted = conn.execute(
        "SELECT 1 FROM medallion_audit.jobs WHERE command_name=? AND scope_ref=? LIMIT 1",
        [COMMAND, "sha256:" + scope],
    ).fetchone()
    existing = conn.execute(
        f"SELECT 1 FROM {store.object_name('event_variants')} "
        "WHERE source=? AND capture_session_id=? LIMIT 1",
        [SOURCE, capture_session_id],
    ).fetchone()
    if attempted is not None or existing is not None:
        raise ValueError("CAPTURE_SESSION_ALREADY_ATTEMPTED")
    config_hash = fingerprint([CAPTURE_VERSION, path, asdict(policy)])
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + scope,
        code_revision=code_revision,
        config_hash=config_hash,
    )
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
        capture = fetcher(credentials, exchange=exchange, policy=policy)
        if capture.path != path or len(capture.raw_body) > policy.max_body_bytes + 1:
            raise ValueError("CAPTURE_ADAPTER_CONTRACT_VIOLATION")
        representation = (
            "http_entity_body_content_coded"
            if capture.body_complete
            else "http_entity_body_incomplete_prefix"
        )
        body = BronzeEvent(
            SOURCE,
            capture_session_id,
            "response-body",
            capture.capture_finished_at,
            capture.raw_body,
            representation,
            "live_provider",
        )
        metadata = capture.metadata()
        metadata.update(
            {
                "metadata_schema_version": 1,
                "capture_session_id": capture_session_id,
                "body_capture_event_id": body.capture_event_id,
                "body_envelope_hash": body.envelope_hash,
                "body_payload_hash": body.payload_hash,
                "policy": asdict(policy),
                "receipt_time_semantics": "LOCAL_CAPTURE_END_NOT_EXCHANGE_OR_PUBLICATION",
            }
        )
        encoded = canonical(metadata)
        if len(encoded) > 32768:
            raise ValueError("CAPTURE_METADATA_BYTE_LIMIT")
        evidence = BronzeEvent(
            SOURCE,
            capture_session_id,
            "response-metadata",
            capture.capture_finished_at,
            encoded,
            "kite_instrument_http_metadata_json@1",
            "live_provider",
        )
        batch = "kite-instrument-http:" + fingerprint(
            [
                body.capture_event_id,
                body.envelope_hash,
                evidence.envelope_hash,
            ]
        )
        receipt = store.append_batch(
            (body, evidence),
            batch_key=batch,
            input_artifact=capture.raw_body,
            job_id=job,
            max_payload_bytes=policy.max_body_bytes + 32768,
        )
        if receipt.conflict_variants:
            raise ValueError("CAPTURE_RECEIPT_CONFLICT")
        result = HttpAcquisitionResult(
            job,
            capture_session_id,
            "CAPTURED" if capture.accepted_transport else "REJECTED",
            capture.disposition_code,
            body.capture_event_id,
            body.envelope_hash,
            evidence.capture_event_id,
            evidence.envelope_hash,
        )
        if not capture.accepted_transport:
            raise HttpAcquisitionRejected(result)
    return result
