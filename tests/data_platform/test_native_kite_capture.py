"""Native journal/callback tests without a broker, SDK or operational database."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import native_kite_capture as module
from nse_quant.data_platform.kite_capture_cli import drive_ticker, main


def journal(tmp_path, **kwargs):
    return module.RawFrameJournal(tmp_path / "session", "session-1", **kwargs)


def append(store, payload=b"\x00raw\xff"):
    return store.append(
        payload,
        received_at=datetime(2026, 10, 30, tzinfo=UTC),
        payload_format="kite_ws_binary_payload",
    )


def read_envelopes(paths):
    return [
        json.loads(line)
        for segment in paths
        for line in segment.path.read_text(encoding="utf-8").splitlines()
    ]


def test_exact_bytes_and_receipt_identity(tmp_path):
    store = journal(tmp_path)
    assert append(store) == "frame-000000000001"
    assert append(store) == "frame-000000000002"
    store.close(clean=True, audit_job_id="job-1")
    segments = module.verify_sealed_session(store.directory)
    events = read_envelopes(segments)
    assert len(events) == 2
    assert all(base64.b64decode(item["payload_base64"]) == b"\x00raw\xff" for item in events)
    assert events[0]["exchange_ts"] is None and events[0]["origin_kind"] == "live_provider"


def test_record_rotation_preserves_order(tmp_path):
    store = journal(tmp_path, max_segment_records=1)
    for _ in range(3):
        append(store)
    store.close(clean=True, audit_job_id="job-1")
    segments = module.verify_sealed_session(store.directory)
    assert len(segments) == 3
    assert [item["source_record_id"] for item in read_envelopes(segments)] == [
        "frame-000000000001",
        "frame-000000000002",
        "frame-000000000003",
    ]


def test_byte_rotation(tmp_path):
    store = journal(tmp_path, max_segment_bytes=2048)
    append(store, b"x" * 800)
    append(store, b"x" * 800)
    store.close(clean=True, audit_job_id="job-1")
    assert len(module.verify_sealed_session(store.directory)) == 2


def test_corrupt_segment_fails(tmp_path):
    store = journal(tmp_path)
    append(store)
    store.close(clean=True, audit_job_id="job-1")
    path = store.directory / "segment-000001.jsonl"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(module.CaptureFailure):
        module.verify_sealed_session(store.directory)


def test_extra_unsealed_file_fails(tmp_path):
    store = journal(tmp_path)
    append(store)
    store.close(clean=True, audit_job_id="job-1")
    (store.directory / "segment-000002.jsonl").write_bytes(b"partial")
    with pytest.raises(module.CaptureFailure, match="Unsealed"):
        module.verify_sealed_session(store.directory)


def test_failed_session_not_drainable(tmp_path):
    store = journal(tmp_path)
    append(store)
    store.close(clean=False, audit_job_id="job-1")
    with pytest.raises(module.CaptureFailure, match="cleanly"):
        module.verify_sealed_session(store.directory)
    assert (store.directory / "segment-000001.jsonl").exists()


def test_fsync_failure_is_fatal_and_bytes_are_not_deleted(tmp_path, monkeypatch):
    store = journal(tmp_path)

    def fail_sync(fd):
        raise OSError("injected fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fsync", fail_sync)
        with pytest.raises(OSError, match="injected"):
            append(store)
    with pytest.raises(module.CaptureFailure):
        append(store)
    store.close(clean=False, audit_job_id="job-1")
    assert (store.directory / "segment-000001.jsonl").stat().st_size > 0
    with pytest.raises(module.CaptureFailure):
        module.verify_sealed_session(store.directory)


def test_session_capacity_fails_closed(tmp_path):
    store = journal(tmp_path, max_segment_bytes=2048, max_session_bytes=2048)
    append(store, b"x" * 800)
    with pytest.raises(module.CaptureFailure, match="budget"):
        append(store, b"x" * 800)
    store.close(clean=False, audit_job_id="job-1")


def test_existing_session_directory_is_not_reused(tmp_path):
    store = journal(tmp_path)
    with pytest.raises(FileExistsError):
        journal(tmp_path)
    store.close(clean=True, audit_job_id="job-1")


def test_closed_journal_rejects_append(tmp_path):
    store = journal(tmp_path)
    store.close(clean=True, audit_job_id="job-1")
    with pytest.raises(module.CaptureFailure):
        append(store)


class FakeTicker:
    MODE_FULL = "full"
    on_message: Callable[..., None] | None = None
    on_connect: Callable[..., None] | None = None
    on_error: Callable[..., None] | None = None
    on_close: Callable[..., None] | None = None

    def __init__(self, connect=True):
        self.connect_ok = connect
        self.subscriptions = []
        self.mode = None
        self.close_calls = 0

    def subscribe(self, tokens):
        self.subscriptions = tokens

    def set_mode(self, mode, tokens):
        self.mode = mode

    def connect(self, threaded):
        assert threaded
        if self.connect_ok:
            assert self.on_connect is not None
            assert self.on_message is not None
            self.on_connect(self, {})
            self.on_message(self, b"raw-binary", True)

    def close(self):
        self.close_calls += 1
        if self.on_close:
            self.on_close(self, 1000, "closed")


def test_native_controller_captures_before_close(tmp_path):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123, 456))
    ticker = FakeTicker()
    drive_ticker(
        ticker,
        callbacks,
        seconds=0.001,
        connect_timeout=0.01,
        close_timeout=0.01,
        request_close=ticker.close,
    )
    assert ticker.subscriptions == [123, 456] and ticker.mode == ticker.MODE_FULL
    assert not callbacks.failed.is_set()
    store.close(clean=True, audit_job_id="job-1")
    item = read_envelopes(module.verify_sealed_session(store.directory))[0]
    assert base64.b64decode(item["payload_base64"]) == b"raw-binary"


def test_frames_during_graceful_shutdown_are_still_persisted(tmp_path):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123,))
    callbacks.stopping.set()
    callbacks.on_message(FakeTicker(), b"last-frame", True)
    store.close(clean=True, audit_job_id="job-1")
    assert len(read_envelopes(module.verify_sealed_session(store.directory))) == 1


def test_text_reencoding_is_explicit(tmp_path):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123,))
    callbacks.on_message(FakeTicker(), "text-message", False)
    store.close(clean=True, audit_job_id="job-1")
    item = read_envelopes(module.verify_sealed_session(store.directory))[0]
    assert item["payload_format"] == "kite_ws_text_reencoded_utf8"


def test_disconnect_is_not_silently_reconnected(tmp_path):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123,))
    ticker = FakeTicker()
    callbacks.on_close(ticker, 1006, "connection lost")
    assert callbacks.failed.is_set() and callbacks.failure_code == "UNEXPECTED_DISCONNECT"
    store.close(clean=False, audit_job_id="job-1")


def test_connect_timeout_is_not_clean(tmp_path):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123,))
    ticker = FakeTicker(connect=False)
    with pytest.raises(module.CaptureFailure, match="connect"):
        drive_ticker(
            ticker,
            callbacks,
            seconds=0.001,
            connect_timeout=0.001,
            close_timeout=0.01,
            request_close=ticker.close,
        )
    store.close(clean=False, audit_job_id="job-1")


def test_persistence_error_stops_callback(tmp_path, monkeypatch):
    store = journal(tmp_path)
    callbacks = module.KiteRawCallbacks(store, (123,))

    def fail_append(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(store, "append", fail_append)
    ticker = FakeTicker()
    with pytest.raises(OSError):
        callbacks.on_message(ticker, b"raw", True)
    assert callbacks.failed.is_set() and ticker.close_calls == 1
    store.close(clean=False, audit_job_id="job-1")


def test_plan_never_creates_files_or_loads_auth(tmp_path, capsys):
    root = tmp_path / "journals"
    assert main(["--tokens", "123", "--journal-root", str(root)]) == 0
    assert '"PLANNED"' in capsys.readouterr().out
    assert not root.exists()


@pytest.mark.parametrize("tokens", [(), (0,), (123, 123)])
def test_invalid_tokens(tmp_path, tokens):
    store = journal(tmp_path)
    with pytest.raises(ValueError):
        module.KiteRawCallbacks(store, tokens)
    store.close(clean=True, audit_job_id="job-1")
