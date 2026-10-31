"""Native raw WebSocket-payload journal, before tick normalization or enrichment.

Synchronous fsync provides explicit backpressure. No volatile accepted-event queue.
Sealed JSONL segments are compatible with the Bronze envelope importer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any, BinaryIO


def file_hash(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _new_json(path: Path, value: object) -> None:
    with path.open("xb") as handle:
        handle.write(_json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())


class CaptureFailure(RuntimeError):
    """Capture is no longer eligible to report a clean session."""


class RawFrameJournal:
    def __init__(
        self,
        session_dir: Path,
        session_id: str,
        *,
        max_segment_bytes: int = 8_388_608,
        max_segment_records: int = 1000,
        max_session_bytes: int = 1_073_741_824,
    ) -> None:
        if not session_id.strip():
            raise ValueError("Session identity is required")
        if not 2048 <= max_segment_bytes <= 8_388_608:
            raise ValueError("Segment limit must be 2 KiB to 8 MiB")
        if not 1 <= max_segment_records <= 1000:
            raise ValueError("Segment record limit must be 1 to 1000")
        if max_session_bytes < max_segment_bytes:
            raise ValueError("Session capacity must cover at least one full segment")
        self.max_session_bytes = max_session_bytes
        self._total_bytes = 0
        self.directory = session_dir
        self.directory.mkdir(parents=True, exist_ok=False)
        self.session_id = session_id
        self.max_segment_bytes = max_segment_bytes
        self.max_segment_records = max_segment_records
        self._lock = Lock()
        self._handle: BinaryIO | None = None
        self._path: Path | None = None
        self._segment_records = 0
        self._segment_bytes = 0
        self._segment_index = 0
        self._total_records = 0
        self._seals: list[str] = []
        self._failed = False
        self._closed = False
        _new_json(
            self.directory / "session_start.json",
            {
                "journal_version": 1,
                "capture_session_id": session_id,
                "source": "kite_websocket",
                "started_at": datetime.now(UTC).isoformat(),
                "max_segment_bytes": max_segment_bytes,
                "max_segment_records": max_segment_records,
                "max_session_bytes": max_session_bytes,
            },
        )

    def _open_segment(self) -> None:
        self._segment_index += 1
        if self._segment_index > 999999:
            raise CaptureFailure("Segment sequence exhausted")
        self._path = self.directory / f"segment-{self._segment_index:06d}.jsonl"
        self._handle = self._path.open("xb", buffering=0)
        self._segment_records = 0
        self._segment_bytes = 0

    def _seal_segment(self) -> None:
        if self._handle is None or self._path is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._handle = None
        seal_name = self._path.name + ".seal.json"
        _new_json(
            self.directory / seal_name,
            {
                "journal_version": 1,
                "capture_session_id": self.session_id,
                "file": self._path.name,
                "sha256": file_hash(self._path),
                "bytes": self._segment_bytes,
                "records": self._segment_records,
            },
        )
        self._seals.append(seal_name)

    def append(self, payload: bytes, *, received_at: datetime, payload_format: str) -> str:
        if not isinstance(payload, bytes) or len(payload) > 1_048_576:
            raise ValueError("Raw payload must be bytes and at most 1 MiB")
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise ValueError("Receipt timestamp must be timezone-aware")
        with self._lock:
            if self._closed or self._failed:
                raise CaptureFailure("Journal is closed or failed")
            record_id = f"frame-{self._total_records + 1:012d}"
            line = (
                _json_bytes(
                    {
                        "envelope_version": 1,
                        "source": "kite_websocket",
                        "capture_session_id": self.session_id,
                        "source_record_id": record_id,
                        "received_at": received_at.astimezone(UTC).isoformat(),
                        "payload_base64": base64.b64encode(payload).decode("ascii"),
                        "payload_format": payload_format,
                        "origin_kind": "live_provider",
                        "exchange_ts": None,
                        "provider_event_id": None,
                        "instrument_ref": None,
                    }
                )
                + b"\n"
            )
            if self._total_bytes + len(line) > self.max_session_bytes:
                self._failed = True
                raise CaptureFailure("Session byte budget exhausted")
            if len(line) > self.max_segment_bytes:
                self._failed = True
                raise CaptureFailure("Frame envelope exceeds segment capacity")
            try:
                if self._handle is not None and (
                    self._segment_bytes + len(line) > self.max_segment_bytes
                    or self._segment_records >= self.max_segment_records
                ):
                    self._seal_segment()
                if self._handle is None:
                    self._open_segment()
                if self._handle is None:
                    raise CaptureFailure("Journal handle unavailable")
                pending = memoryview(line)
                while pending:
                    written = self._handle.write(pending)
                    if written is None or written <= 0:
                        raise OSError("Short journal write")
                    pending = pending[written:]
                self._handle.flush()
                os.fsync(self._handle.fileno())
                self._segment_records += 1
                self._segment_bytes += len(line)
                self._total_records += 1
                self._total_bytes += len(line)
                return record_id
            except BaseException:
                self._failed = True
                raise

    def close(self, *, clean: bool, audit_job_id: str) -> None:
        with self._lock:
            if self._closed:
                raise CaptureFailure("Session already closed")
            if clean and not self._failed:
                try:
                    self._seal_segment()
                except BaseException:
                    self._failed = True
                    raise
            elif self._handle is not None:
                self._handle.close()
                self._handle = None
            status = "CLOSED" if clean and not self._failed else "FAILED"
            _new_json(
                self.directory / "session_final.json",
                {
                    "journal_version": 1,
                    "capture_session_id": self.session_id,
                    "status": status,
                    "records": self._total_records,
                    "seals": self._seals,
                    "audit_job_id": audit_job_id,
                    "closed_at": datetime.now(UTC).isoformat(),
                },
            )
            self._closed = True


class KiteRawCallbacks:
    def __init__(self, journal: RawFrameJournal, tokens: tuple[int, ...]) -> None:
        if not tokens or any(type(token) is not int or token <= 0 for token in tokens):
            raise ValueError("Positive instrument tokens are required")
        if len(set(tokens)) != len(tokens):
            raise ValueError("Duplicate subscription tokens")
        self.journal = journal
        self.tokens = tokens
        self.connected = Event()
        self.closed = Event()
        self.stopping = Event()
        self.failed = Event()
        self.failure_code: str | None = None

    def _fail(self, client: Any, code: str) -> None:
        if self.failure_code is None:
            self.failure_code = code
        first_failure = not self.failed.is_set()
        self.failed.set()
        if first_failure:
            with suppress(Exception):
                client.close()

    def on_connect(self, client: Any, response: Any) -> None:
        try:
            client.subscribe(list(self.tokens))
            client.set_mode(client.MODE_FULL, list(self.tokens))
            self.connected.set()
        except Exception:
            self._fail(client, "SUBSCRIPTION_FAILED")
            raise

    def on_message(self, client: Any, payload: Any, is_binary: bool) -> None:
        received_at = datetime.now(UTC)
        if self.failed.is_set():
            raise CaptureFailure("Capture has failed")
        try:
            if isinstance(payload, bytes):
                raw = payload
                representation = "kite_ws_binary_payload" if is_binary else "kite_ws_text_bytes"
            elif isinstance(payload, str) and not is_binary:
                raw = payload.encode("utf-8")
                representation = "kite_ws_text_reencoded_utf8"
            else:
                raise TypeError("Unsupported SDK payload representation")
            self.journal.append(raw, received_at=received_at, payload_format=representation)
        except Exception:
            self._fail(client, "RAW_CAPTURE_FAILED")
            raise

    def on_error(self, client: Any, code: Any, reason: Any) -> None:
        self._fail(client, "SDK_ERROR")

    def on_close(self, client: Any, code: Any, reason: Any) -> None:
        self.closed.set()
        self.connected.clear()
        if not self.stopping.is_set():
            self._fail(client, "UNEXPECTED_DISCONNECT")


@dataclass(frozen=True)
class VerifiedSegment:
    path: Path
    sha256: str
    records: int


def verify_sealed_session(session_dir: Path) -> tuple[VerifiedSegment, ...]:
    if session_dir.is_symlink() or any(
        (session_dir / name).is_symlink() for name in ("session_start.json", "session_final.json")
    ):
        raise CaptureFailure("Symlinked session metadata is not accepted")
    final = json.loads((session_dir / "session_final.json").read_text(encoding="utf-8"))
    start = json.loads((session_dir / "session_start.json").read_text(encoding="utf-8"))
    if final["status"] != "CLOSED" or final["journal_version"] != 1:
        raise CaptureFailure("Only cleanly closed version-1 sessions can be drained")
    if final["capture_session_id"] != start["capture_session_id"]:
        raise CaptureFailure("Session identities disagree")
    paths = []
    total = 0
    expected = 1
    for seal_name in final["seals"]:
        wanted = f"segment-{expected:06d}.jsonl.seal.json"
        if seal_name != wanted:
            raise CaptureFailure("Missing, repeated or reordered segment seal")
        seal_path = session_dir / seal_name
        if seal_path.is_symlink():
            raise CaptureFailure("Symlinked seal is not accepted")
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        if seal["capture_session_id"] != final["capture_session_id"]:
            raise CaptureFailure("Seal belongs to another capture session")
        filename = seal["file"]
        if re.fullmatch(r"segment-[0-9]{6}\.jsonl", filename) is None:
            raise CaptureFailure("Invalid segment path")
        if filename + ".seal.json" != seal_name:
            raise CaptureFailure("Segment name mismatch")
        path = session_dir / filename
        if path.is_symlink() or path.stat().st_size != seal["bytes"]:
            raise CaptureFailure("Segment file/size mismatch")
        if path.stat().st_size > 8_388_608 or file_hash(path) != seal["sha256"]:
            raise CaptureFailure("Segment capacity/checksum mismatch")
        records = 0
        with path.open("rb") as handle:
            for line in handle:
                envelope = json.loads(line)
                records += 1
                wanted_record = f"frame-{total + records:012d}"
                if (
                    envelope["source_record_id"] != wanted_record
                    or envelope["capture_session_id"] != final["capture_session_id"]
                    or envelope["source"] != "kite_websocket"
                    or envelope["origin_kind"] != "live_provider"
                ):
                    raise CaptureFailure("Envelope identity/order mismatch")
                base64.b64decode(envelope["payload_base64"], validate=True)
        if records != seal["records"] or not 1 <= records <= 1000:
            raise CaptureFailure("Segment record count mismatch")
        total += records
        paths.append(VerifiedSegment(path, seal["sha256"], records))
        expected += 1
    if total != final["records"]:
        raise CaptureFailure("Session record total mismatch")
    declared = {segment.path.name for segment in paths}
    actual = {path.name for path in session_dir.glob("segment-*.jsonl")}
    if actual != declared:
        raise CaptureFailure("Unsealed or unlisted segment remains")
    return tuple(paths)
