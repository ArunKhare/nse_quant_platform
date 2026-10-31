"""Append-only application audit API for a single-owner DuckDB connection.

This is not a database permission boundary or a domain-data publication transaction.
Do not share the connection across other writer processes or external transactions.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from uuid import uuid4

import duckdb

from nse_quant.data_platform.contracts import DatasetContract


class JobState(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    STAGED = "STAGED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_NEXT = {
    JobState.PLANNED: {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED},
    JobState.RUNNING: {
        JobState.STAGED,
        JobState.SUCCEEDED,
        JobState.CANCELLED,
        JobState.FAILED,
    },
    JobState.STAGED: {JobState.VALIDATED, JobState.CANCELLED, JobState.FAILED},
    JobState.VALIDATED: {JobState.PUBLISHED, JobState.CANCELLED, JobState.FAILED},
    JobState.PUBLISHED: {JobState.SUCCEEDED, JobState.FAILED},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


class AuditLedger:
    """Explicitly initialized foundation ledger; caller owns the connection."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn
        self._lock = Lock()

    def initialize(self) -> None:
        """Create only new audit objects. Never called implicitly by readers."""
        with self._lock:
            self.conn.execute("BEGIN TRANSACTION")
            try:
                self.conn.execute("CREATE SCHEMA IF NOT EXISTS medallion_audit")
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS medallion_audit.schema_versions (
                        version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                versions = self.conn.execute(
                    "SELECT version FROM medallion_audit.schema_versions"
                ).fetchall()
                if versions and versions != [(1,)]:
                    raise ValueError("Unsupported audit schema version")
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS medallion_audit.dataset_contracts (
                        dataset_name VARCHAR NOT NULL,
                        contract_version VARCHAR NOT NULL,
                        fingerprint VARCHAR NOT NULL,
                        contract_json VARCHAR NOT NULL,
                        registered_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (dataset_name, contract_version)
                    )
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS medallion_audit.jobs (
                        job_id VARCHAR PRIMARY KEY,
                        parent_job_id VARCHAR,
                        command_name VARCHAR NOT NULL,
                        actor_id VARCHAR NOT NULL,
                        scope_ref VARCHAR NOT NULL,
                        code_revision VARCHAR NOT NULL,
                        config_hash VARCHAR NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS medallion_audit.job_events (
                        job_id VARCHAR NOT NULL,
                        event_index INTEGER NOT NULL,
                        state VARCHAR NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        reason_code VARCHAR,
                        PRIMARY KEY (job_id, event_index)
                    )
                    """
                )
                if not versions:
                    self.conn.execute(
                        "INSERT INTO medallion_audit.schema_versions VALUES (1, ?)",
                        [datetime.now(UTC)],
                    )
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def register_contract(self, contract: DatasetContract) -> bool:
        """Return False for exact retry; reject an incompatible same-version contract."""
        with self._lock:
            row = self.conn.execute(
                """
                SELECT fingerprint FROM medallion_audit.dataset_contracts
                WHERE dataset_name = ? AND contract_version = ?
                """,
                [contract.name, contract.version],
            ).fetchone()
            if row:
                if row[0] != contract.fingerprint:
                    raise ValueError("Contract changed without a version increment")
                return False
            self.conn.execute(
                """
                INSERT INTO medallion_audit.dataset_contracts VALUES (?, ?, ?, ?, ?)
                """,
                [
                    contract.name,
                    contract.version,
                    contract.fingerprint,
                    contract.canonical_json(),
                    datetime.now(UTC),
                ],
            )
            return True

    def plan_job(
        self,
        *,
        command_name: str,
        actor_id: str,
        scope_ref: str,
        code_revision: str,
        config_hash: str,
        parent_job_id: str | None = None,
    ) -> str:
        """Store identifiers only: no argv, payloads, exception messages, or secrets."""
        if any(
            not value.strip()
            for value in (
                command_name,
                actor_id,
                scope_ref,
                code_revision,
                config_hash,
            )
        ):
            raise ValueError("All execution identifiers must be nonempty")
        job_id = str(uuid4())
        with self._lock:
            self.conn.execute("BEGIN TRANSACTION")
            try:
                if parent_job_id is not None:
                    parent = self.conn.execute(
                        "SELECT 1 FROM medallion_audit.jobs WHERE job_id = ?",
                        [parent_job_id],
                    ).fetchone()
                    if parent is None:
                        raise ValueError("Parent job does not exist")
                now = datetime.now(UTC)
                self.conn.execute(
                    "INSERT INTO medallion_audit.jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        job_id,
                        parent_job_id,
                        command_name,
                        actor_id,
                        scope_ref,
                        code_revision,
                        config_hash,
                        now,
                    ],
                )
                self.conn.execute(
                    "INSERT INTO medallion_audit.job_events VALUES (?, 1, ?, ?, NULL)",
                    [job_id, JobState.PLANNED.value, now],
                )
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        return job_id

    def transition(self, job_id: str, state: JobState, reason_code: str | None = None) -> None:
        if not isinstance(state, JobState):
            raise TypeError("Use a JobState enum value")
        if reason_code is not None and (
            not reason_code
            or len(reason_code) > 64
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in reason_code)
        ):
            raise ValueError("Reason must be a short uppercase code, not free text")
        with self._lock:
            row = self.conn.execute(
                """
                SELECT event_index, state FROM medallion_audit.job_events
                WHERE job_id = ? ORDER BY event_index DESC LIMIT 1
                """,
                [job_id],
            ).fetchone()
            if row is None:
                raise ValueError("Unknown job")
            if state not in _NEXT[JobState(row[1])]:
                raise ValueError(f"Invalid transition: {row[1]} -> {state.value}")
            self.conn.execute(
                "INSERT INTO medallion_audit.job_events VALUES (?, ?, ?, ?, ?)",
                [job_id, row[0] + 1, state.value, datetime.now(UTC), reason_code],
            )

    @contextmanager
    def execution(self, job_id: str) -> Iterator[str]:
        """Audit one run; domain rollback remains the job implementation's responsibility."""
        self.transition(job_id, JobState.RUNNING)
        try:
            yield job_id
        except BaseException as error:
            state = JobState.CANCELLED if isinstance(error, KeyboardInterrupt) else JobState.FAILED
            code = "INTERRUPTED" if state == JobState.CANCELLED else "EXECUTION_ERROR"
            try:
                self.transition(job_id, state, code)
            except Exception as audit_error:
                error.add_note(f"Audit failure: {type(audit_error).__name__}")
            raise
        else:
            self.transition(job_id, JobState.SUCCEEDED)
