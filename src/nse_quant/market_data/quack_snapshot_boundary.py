"""Opt-in dedicated Quack boundary. Never import from runner entry points yet."""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from nse_quant.market_data.market_snapshot_service import MAX_BYTES, READ_SQL, read_snapshot


class SnapshotPublisher:
    """One process/thread owns connection and serializes publish/start/stop calls."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.pid = os.getpid()
        self.last_capture: datetime | None = None

    def _owned(self) -> None:
        if os.getpid() != self.pid:
            raise RuntimeError("publisher_process_mismatch")

    def initialize(self) -> None:
        self._owned()
        self.connection.execute(
            "CREATE TABLE market_snapshot_slot (slot INTEGER PRIMARY KEY CHECK(slot=1), payload VARCHAR NOT NULL)"
        )

    def publish(
        self,
        snapshot: dict[str, Any],
        *,
        underlying: str,
        expected_tokens: frozenset[int],
        as_of: datetime,
        max_age: timedelta,
    ) -> None:
        self._owned()
        raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError("snapshot_size")
        captured = datetime.fromisoformat(snapshot["captured_at"])
        if captured.utcoffset() is None or (self.last_capture is not None and captured <= self.last_capture):
            raise ValueError("capture_not_strictly_advancing")
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self.connection.execute("DELETE FROM market_snapshot_slot")
            self.connection.execute("INSERT INTO market_snapshot_slot VALUES (1, ?)", [raw])
            read_snapshot(
                self.connection, underlying=underlying, expected_tokens=expected_tokens, as_of=as_of, max_age=max_age
            )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        self.last_capture = captured


def serve(connection: Any, *, port: int) -> tuple[str, str]:
    """Dedicated fresh in-memory DuckDB instance only; return secret to supervisor."""
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("invalid_loopback_port")
    connection.execute("LOAD httpfs")
    connection.execute("LOAD quack")
    query = READ_SQL.replace("'", "''")
    connection.execute(f"CREATE MACRO market_snapshot_authorize(sid, query) AS (query = '{query}')")
    connection.execute("SET GLOBAL quack_authorization_function='market_snapshot_authorize'")
    uri, token = f"quack:127.0.0.1:{port}", secrets.token_urlsafe(32)
    connection.execute("CALL quack_serve(?, token => ?)", [uri, token]).fetchall()
    return uri, token


class QuackSnapshotSession:
    """Own an isolated client connection; submit SQL through quack_query."""

    def __init__(self, connection: Any, uri: str, token: str) -> None:
        self._connection = connection
        self._uri = uri
        self._token = token

    def execute(self, sql: str) -> SnapshotRows:
        rows = self._connection.execute(
            "SELECT * FROM quack_query(?, ?, token => ?)",
            [self._uri, sql, self._token],
        ).fetchall()
        return SnapshotRows(rows)

    def close(self) -> None:
        self._connection.close()


def connect_reader(uri: str, token: str) -> QuackSnapshotSession:
    """Create a local session without remote catalog attachment.

    Authentication and authorization occur when a remote query is issued.
    The caller owns and closes the returned session.
    """
    if (
        re.fullmatch(r"quack:127\.0\.0\.1:[0-9]{4,5}", uri) is None
        or not 1024 <= int(uri.rsplit(":", 1)[1]) <= 65535
        or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None
    ):
        raise ValueError("invalid_endpoint_or_token")

    import duckdb

    connection = duckdb.connect(":memory:")
    try:
        connection.execute("LOAD httpfs")
        connection.execute("LOAD quack")
        return QuackSnapshotSession(connection, uri, token)
    except BaseException:
        connection.close()
        raise


class SnapshotRows:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self._offset = 0

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        rows = self._rows[self._offset : self._offset + size]
        self._offset += len(rows)
        return rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self._rows[self._offset :]
        self._offset = len(self._rows)
        return rows
