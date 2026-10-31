"""Bounded native Kite capture. No auth/network/directory creation in default plan mode."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from nse_quant.data_platform.native_kite_capture import (
    CaptureFailure,
    KiteRawCallbacks,
    RawFrameJournal,
)


def drive_ticker(
    ticker: Any,
    callbacks: KiteRawCallbacks,
    *,
    seconds: float,
    connect_timeout: float,
    close_timeout: float,
    request_close: Any,
) -> None:
    if not hasattr(ticker, "on_message"):
        raise CaptureFailure("Installed SDK does not expose the required raw-message callback")
    ticker.on_message = callbacks.on_message
    ticker.on_connect = callbacks.on_connect
    ticker.on_error = callbacks.on_error
    ticker.on_close = callbacks.on_close
    had_error = False
    try:
        ticker.connect(threaded=True)
        deadline = time.monotonic() + connect_timeout
        while not callbacks.connected.is_set():
            if callbacks.failed.is_set() or time.monotonic() >= deadline:
                raise CaptureFailure("Raw capture did not connect cleanly")
            callbacks.connected.wait(0.05)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if callbacks.failed.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
                raise CaptureFailure("Raw capture failed; inspect session audit")
    except BaseException:
        had_error = True
        callbacks.failed.set()
        raise
    finally:
        callbacks.stopping.set()
        try:
            request_close()
        except Exception:
            callbacks.failed.set()
            if not had_error:
                raise CaptureFailure("SDK close request failed") from None
        if not callbacks.closed.wait(close_timeout) and not had_error:
            callbacks.failed.set()
            raise CaptureFailure("SDK did not confirm connection close")
    if callbacks.failed.is_set():
        raise CaptureFailure("Session contains a capture/connection failure")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", nargs="+", type=int, required=True)
    parser.add_argument("--journal-root", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--close-timeout", type=float, default=10.0)
    parser.add_argument("--max-session-bytes", type=int, default=1_073_741_824)
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if (
        not args.tokens
        or any(token <= 0 for token in args.tokens)
        or len(set(args.tokens)) != len(args.tokens)
    ):
        parser.error("Use distinct positive instrument tokens")
    if any(
        not 0 < value < float("inf")
        for value in (
            args.seconds,
            args.connect_timeout,
            args.close_timeout,
        )
    ):
        parser.error("Durations must be finite positive values")
    if args.max_session_bytes < 8_388_608:
        parser.error("Session budget must be at least 8 MiB")
    plan = {
        "command": "capture.kite_raw@1",
        "tokens": sorted(args.tokens),
        "seconds": args.seconds,
        "journal_root": str(args.journal_root.resolve()),
        "connect_timeout": args.connect_timeout,
        "close_timeout": args.close_timeout,
        "max_session_bytes": args.max_session_bytes,
        "auto_reconnect": False,
        "code_revision": args.code_revision,
        "actor": args.actor,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}, indent=2))
        return 0
    if not args.code_revision.strip() or not args.actor.strip():
        parser.error("Execution requires actor and code revision")
    import duckdb
    from kiteconnect import KiteTicker
    from twisted.internet import reactor

    from nse_quant.core.settings import get_settings
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.manifests import ManifestStore
    from nse_quant.integrations.kite_auth import get_authenticated_kite

    session_id = uuid4().hex
    directory = args.journal_root.resolve() / session_id
    journal = RawFrameJournal(directory, session_id, max_session_bytes=args.max_session_bytes)
    conn = duckdb.connect(str(directory / "audit.duckdb"))
    job: str | None = None
    try:
        ledger = AuditLedger(conn)
        ledger.initialize()
        manifests = ManifestStore(directory / "manifests")
        payload = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        manifests.put(payload)
        job = ledger.plan_job(
            command_name="capture.kite_raw@1",
            actor_id=args.actor,
            scope_ref="sha256:" + hashlib.sha256(payload).hexdigest(),
            code_revision=args.code_revision,
            config_hash=hashlib.sha256(b"kite-raw-journal-v1;fsync-every-frame").hexdigest(),
        )
        with ledger.execution(job):
            try:
                settings = get_settings()
                kite = get_authenticated_kite()
                ticker = KiteTicker(
                    settings.secrets.kite_api_key,
                    kite.access_token,
                    reconnect=False,
                )
                callbacks = KiteRawCallbacks(journal, tuple(args.tokens))

                def request_close() -> None:
                    reactor.callFromThread(ticker.close)

                drive_ticker(
                    ticker,
                    callbacks,
                    seconds=args.seconds,
                    connect_timeout=args.connect_timeout,
                    close_timeout=args.close_timeout,
                    request_close=request_close,
                )
            except BaseException:
                with suppress(Exception):
                    journal.close(clean=False, audit_job_id=job)
                raise
            journal.close(clean=True, audit_job_id=job)
            receipt = {
                "session_id": session_id,
                "audit_job_id": job,
                "session_dir": str(directory),
                "closed_at": datetime.now(UTC).isoformat(),
                "sdk_version": importlib.metadata.version("kiteconnect"),
            }
            manifests.put(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
        print(json.dumps({"status": "CLOSED", **receipt}, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
