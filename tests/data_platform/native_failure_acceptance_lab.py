"""Real-producer disposable lab; reopen owners between fault injection and readers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
from native_acceptance_case import NativeAcceptanceCase

from nse_quant.data_platform import admission_capture as capture
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.admission_capture_reader import read_admission_capture
from nse_quant.data_platform.admission_frontier import observe_admission_frontier
from nse_quant.data_platform.admission_revalidation import revalidate_captured_publication_use
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.gold_quote_reader import read_quote_price_build
from nse_quant.data_platform.quote_bundle_stage_reader import read_staged_quote_bundle
from nse_quant.data_platform.quote_publication_reader import read_research_publication


def table(conn: Any, schema: str, name: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    assert row is not None
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, name))


class NativeFailureLab:
    """The only seed is the accepted real producer fixture, not synthetic SQL success rows."""

    def __init__(self, root: Path) -> None:
        with ExitStack() as stack:
            case = NativeAcceptanceCase(root, stack)
            result = case.run(stack)
            self.paths = dict(case.paths)
            self.at = case.at
            self.identity = dict(case.identity)
            self.artifacts = case.artifacts
            self.original = result["receipt"]
            self.raw = result["raw"]
            self.capture = dict(result["capture"])
            self.build_id = result["build"]["build_id"]
            self.bundle_id = result["current"].bundle_id
        self.publication_id = self.original.publication_id

    @contextmanager
    def opened(self, *roles: str, writable: bool = False) -> Iterator[tuple[Any, ...]]:
        with ExitStack() as stack:
            handles: list[Any] = []
            for role in roles:
                conn = duckdb.connect(str(self.paths[role]), read_only=not writable)
                stack.callback(conn.close)
                handles.append(conn)
            yield tuple(handles)

    def replay(self) -> Any:
        value = policy.replay_admission_receipt(
            self.raw,
            expected_receipt_id=self.original.receipt_id,
        )
        assert value == self.original
        return value

    def archived(self) -> Any:
        with self.opened("captures") as (conn,):
            return read_admission_capture(conn, receipt_id=self.original.receipt_id)

    def publication(self) -> Any:
        with self.opened("publications") as (conn,):
            return read_research_publication(conn, publication_id=self.publication_id)

    def frontier(self) -> Any:
        with self.opened("captures") as (conn,):
            return observe_admission_frontier(conn)

    def revalidate(self, request: policy.AdmissionRequest | None = None) -> Any:
        with self.opened("publications", "captures") as (publications, captures):
            return revalidate_captured_publication_use(
                publications,
                captures,
                receipt_id=self.original.receipt_id,
                publication_id=self.publication_id,
                request=request or policy.AdmissionRequest(policy.POINT_IN_TIME, self.at, self.at),
            )

    def gold(self) -> Any:
        with self.opened("bronze", "frames", "references", "assessments", "gold") as handles:
            return read_quote_price_build(*handles, build_id=self.build_id)

    def stage(self) -> Any:
        with self.opened(
            "bronze",
            "frames",
            "references",
            "assessments",
            "gold",
            "staging",
        ) as handles:
            return read_staged_quote_bundle(
                *handles,
                bundle_id=self.bundle_id,
                artifact_root=self.artifacts,
            )

    def retry(self) -> dict[str, object]:
        with (
            self.opened("publications") as (publications,),
            self.opened(
                "captures",
                writable=True,
            ) as (captures,),
        ):
            return capture.capture_publication_admission(
                publications,
                captures,
                publication_id=self.publication_id,
                request=policy.AdmissionRequest(policy.POINT_IN_TIME, self.at, self.at),
                initialize=False,
                **self.identity,
            )

    def add_scoped_job(self, terminal: JobState | None) -> str:
        with self.opened("captures", writable=True) as (conn,):
            ledger = AuditLedger(conn)
            versions = [
                capture.STORE_VERSION,
                policy.POLICY_VERSION,
                policy.DEFINITION_FINGERPRINT,
                capture.CONTRACT_FINGERPRINT,
            ]
            job = ledger.plan_job(
                command_name=capture.COMMAND,
                **self.identity,
                scope_ref="sha256:" + self.capture["request_revision_id"],
                config_hash=capture._hash(versions),
            )
            ledger.transition(job, JobState.RUNNING)
            if terminal is not None:
                ledger.transition(
                    job,
                    terminal,
                    "INTERRUPTED" if terminal == JobState.CANCELLED else "EXECUTION_ERROR",
                )
            return job

    def append_frame_conflict(self) -> None:
        with self.opened("bronze", writable=True) as (conn,):
            events = table(conn, "bronze", "event_variants")
            row = conn.execute(
                f"SELECT source,capture_session_id,source_record_id,received_at,payload,"
                f"payload_format,origin_kind FROM {events} WHERE source='kite_websocket'"
            ).fetchone()
            assert row is not None
            original = BronzeEvent(*row[:4], bytes(row[4]), *row[5:])
            changed = replace(original, payload=original.payload[:-1] + b"\x00")
            assert original.payload != changed.payload
            ledger = AuditLedger(conn)
            job = ledger.plan_job(
                command_name="synthetic.acceptance_conflict@1",
                **self.identity,
                scope_ref="sha256:" + original.capture_event_id,
                config_hash=hashlib_sha(changed.payload),
            )
            with ledger.execution(job):
                receipt = BronzeEventStore(conn).append_batch(
                    (changed,),
                    batch_key="acceptance-conflict",
                    input_artifact=changed.payload,
                    job_id=job,
                )
            assert receipt.conflict_variants == 1


def hashlib_sha(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()
