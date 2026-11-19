"""Disposable native producer path. No source readers or computations substituted."""

from __future__ import annotations

import hashlib
import json
import struct
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from nse_quant.data_platform.admission_capture import capture_publication_admission
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.gold_quote_store import persist_quote_price_build
from nse_quant.data_platform.kite_silver import normalize_variant
from nse_quant.data_platform.native_reference_evidence import ReferencePins, inspect_reference_pair
from nse_quant.data_platform.native_reference_silver import normalize_http_reference
from nse_quant.data_platform.packet_association_silver import persist_packet_association
from nse_quant.data_platform.publication_admission import (
    POINT_IN_TIME,
    AdmissionRequest,
    replay_admission_receipt,
)
from nse_quant.data_platform.quote_bundle_publication import publish_research_quote_bundle
from nse_quant.data_platform.quote_bundle_stage_reader import read_staged_quote_bundle
from nse_quant.data_platform.quote_bundle_staging import stage_quote_bundle


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class NativeAcceptanceCase:
    """Test-only owner of eight disposable DBs; never points at configured user data."""

    def __init__(self, root: Path, stack: ExitStack) -> None:
        self.root = root
        self.paths = {
            role: root / (role + ".duckdb")
            for role in (
                "bronze",
                "frames",
                "references",
                "assessments",
                "gold",
                "staging",
                "publications",
                "captures",
            )
        }
        self.db: dict[str, Any] = {}
        for role, path in self.paths.items():
            self.db[role] = stack.enter_context(duckdb.connect(str(path)))
        self.at = datetime(2026, 1, 1, tzinfo=UTC)
        self.identity = dict(actor_id="synthetic-acceptance", code_revision="synthetic-fixture-v1")
        self.artifacts = root / "artifacts"

    def readonly(self, role: str, stack: ExitStack) -> Any:
        self.db[role].close()
        return stack.enter_context(duckdb.connect(str(self.paths[role]), read_only=True))

    def seed(self) -> tuple[BronzeEvent, ReferencePins]:
        """Create synthetic wire-format evidence, not authenticated provider observations.

        The current reader requires live_provider in its envelope schema. Here this
        is solely a disposable contract fixture, never a real acquisition claim.
        """
        conn = self.db["bronze"]
        store = BronzeEventStore(conn)
        store.initialize()
        ledger = AuditLedger(conn)
        ledger.initialize()
        csv = (
            b"instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,"
            b"strike,tick_size,lot_size,instrument_type,segment,exchange\n"
            b"257,1,SYNTHETIC,SYNTHETIC,123.45,,0,0.05,1,EQ,NSE,NSE\n"
        )
        body = BronzeEvent(
            "kite_instruments_http",
            "synthetic-http",
            "response-body",
            self.at,
            csv,
            "http_entity_body_content_coded",
            "live_provider",
        )
        policy = dict(
            max_body_bytes=8388608,
            chunk_bytes=65536,
            connect_timeout_seconds=10,
            read_timeout_seconds=10,
            elapsed_budget_seconds=30,
        )
        meta: dict[str, object] = dict(
            metadata_schema_version=1,
            capture_version="kite-instrument-http@2",
            body_capture_event_id=body.capture_event_id,
            body_envelope_hash=body.envelope_hash,
            body_payload_hash=body.payload_hash,
            captured_body_hash=body.payload_hash,
            capture_session_id=body.capture_session_id,
            body_bytes=len(csv),
            host="api.kite.trade",
            method="GET",
            path="/instruments",
            policy=policy,
            status_code=200,
            headers_complete=True,
            body_complete=True,
            body_observed=True,
            transport_accepted=True,
            payload_is_incomplete=False,
            returned_bytes_not_retained=0,
            reason_code="COMPLETE",
            disposition_code="UNVALIDATED_HTTP_CAPTURE",
            csv_validated=False,
            body_representation="HTTP_ENTITY_BODY_CONTENT_CODING_PRESERVED",
            header_scope="SELECTED_ALLOWLIST_ONLY_NOT_RAW_HEADERS",
            provider_published_at=None,
            platform_published_at=None,
            receipt_time_semantics="LOCAL_CAPTURE_END_NOT_EXCHANGE_OR_PUBLICATION",
            selected_headers=[["content-type", "text/csv"], ["content-length", str(len(csv))]],
        )
        for key in (
            "request_started_at",
            "headers_received_at",
            "first_chunk_returned_at",
            "capture_finished_at",
        ):
            meta[key] = self.at.isoformat()
        metadata = BronzeEvent(
            body.source,
            body.capture_session_id,
            "response-metadata",
            self.at,
            canonical(meta).encode(),
            "kite_instrument_http_metadata_json@1",
            "live_provider",
        )
        job = ledger.plan_job(
            command_name="ingest.kite_instruments_http@1",
            **self.identity,
            scope_ref="sha256:" + digest([body.source, body.capture_session_id]),
            config_hash=digest(["kite-instrument-http@2", "/instruments", policy]),
        )
        with ledger.execution(job):
            store.append_batch(
                (body, metadata), batch_key="synthetic-http", input_artifact=csv, job_id=job
            )
        frame = BronzeEvent(
            "kite_websocket",
            "synthetic-ws",
            "frame-0",
            self.at,
            struct.pack(">HHII", 1, 8, 257, 12345),
            "binary",
            "live_provider",
        )
        job = ledger.plan_job(
            command_name="synthetic.received_frame@1",
            **self.identity,
            scope_ref="sha256:" + frame.capture_event_id,
            config_hash=digest(["synthetic"]),
        )
        with ledger.execution(job):
            store.append_batch(
                (frame,), batch_key="synthetic-ws", input_artifact=frame.payload, job_id=job
            )
        return frame, ReferencePins(
            body.capture_event_id,
            body.envelope_hash,
            metadata.capture_event_id,
            metadata.envelope_hash,
        )

    def run(self, stack: ExitStack) -> dict[str, Any]:
        frame, pins = self.seed()
        bronze = self.readonly("bronze", stack)
        pair = inspect_reference_pair(bronze, pins)
        assert pair.gate_code == "VERIFIED"
        frame_revision = normalize_variant(
            bronze,
            self.db["frames"],
            capture_event_id=frame.capture_event_id,
            envelope_hash=frame.envelope_hash,
            initialize=True,
            **self.identity,
        )
        reference = normalize_http_reference(
            bronze,
            self.db["references"],
            pins=pins,
            initialize=True,
            **self.identity,
        )
        assert reference["classification"] == "normalized"
        frames = self.readonly("frames", stack)
        references = self.readonly("references", stack)
        association = persist_packet_association(
            bronze,
            frames,
            references,
            self.db["assessments"],
            frame_revision_id=frame_revision,
            packet_ordinal=0,
            reference_assessment_revision_id=reference["revision_id"],
            initialize=True,
            **self.identity,
        )
        assert association["status"] == "associated"
        assessments = self.readonly("assessments", stack)
        sources = (bronze, frames, references, assessments)
        build = persist_quote_price_build(
            *sources,
            self.db["gold"],
            assessment_revision_id=association["revision_id"],
            initialize=True,
            **self.identity,
        )
        assert build["status"] == "candidate"
        gold = self.readonly("gold", stack)
        stage = stage_quote_bundle(
            *sources,
            gold,
            self.db["staging"],
            build_ids=(build["build_id"],),
            artifact_root=self.artifacts,
            initialize=True,
            **self.identity,
        )
        staging = self.readonly("staging", stack)
        current = read_staged_quote_bundle(
            *sources,
            gold,
            staging,
            bundle_id=stage["bundle_id"],
            artifact_root=self.artifacts,
        )
        assert current.status == "verified_current"
        publication = publish_research_quote_bundle(
            *sources,
            gold,
            staging,
            self.db["publications"],
            bundle_id=stage["bundle_id"],
            artifact_root=self.artifacts,
            expected_stage_evidence_fingerprint=current.evidence_fingerprint,
            purpose="RESEARCH_ONLY",
            allow_publication=True,
            initialize=True,
            **self.identity,
        )
        publications = self.readonly("publications", stack)
        capture = capture_publication_admission(
            publications,
            self.db["captures"],
            publication_id=publication["publication_id"],
            request=AdmissionRequest(POINT_IN_TIME, self.at, self.at),
            initialize=True,
            **self.identity,
        )
        conn = self.db["captures"]
        row = conn.execute(
            'SELECT receipt_id,receipt_bytes FROM "captures"."decision_inputs".'
            '"admission_receipts" WHERE receipt_id=?',
            [capture["receipt_id"]],
        ).fetchone()
        assert row is not None
        raw = bytes(row[1])
        receipt = replay_admission_receipt(raw, expected_receipt_id=row[0])
        assert receipt.status == "REJECTED"
        assert receipt.decision_eligibility_asserted is False
        return dict(
            receipt=receipt,
            raw=raw,
            capture=capture,
            pair=pair,
            build=build,
            current=current,
            sources=sources,
            gold=gold,
        )
