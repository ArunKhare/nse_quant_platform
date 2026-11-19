"""Requires real project AuditLedger and Bronze APIs; not sandbox-executed."""

import json
import struct
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.kite_silver import name, normalize_variant


def test_lineage_retry_versions(tmp_path, monkeypatch):
    b = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    s = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        store = BronzeEventStore(b)
        store.initialize()
        e = BronzeEvent(
            "kite_websocket",
            "session",
            "r",
            datetime.now(UTC),
            struct.pack(">HHII", 1, 8, 258, 12345),
            "kite_ws_binary_payload",
            "live_provider",
        )
        store.append_batch((e,), batch_key="test", input_artifact=b"fixture", job_id="fixture")
        table = store.object_name("event_variants")
        before = b.execute(f"SELECT * FROM {table}").fetchall()
        kw = dict(
            capture_event_id=e.capture_event_id,
            envelope_hash=e.envelope_hash,
            actor_id="test",
            code_revision="fixture",
        )
        r = normalize_variant(b, s, initialize=True, **kw)
        assert normalize_variant(b, s, **kw) == r
        target = name(s, "silver", "kite_frames")
        rows = s.execute(f"SELECT * FROM {target}").fetchall()
        assert len(rows) == 1
        assert rows[0][1:4] == (e.capture_event_id, e.envelope_hash, e.payload_hash)
        assert rows[0][9] is None
        assert json.loads(rows[0][12])["packets"][0]["instrument_token"] == 258
        monkeypatch.setattr("nse_quant.data_platform.kite_silver.DECODER_VERSION", "test-next@2")
        assert normalize_variant(b, s, **kw) != r
        assert s.execute(f"SELECT count(*) FROM {target}").fetchone() == (2,)
        assert b.execute(f"SELECT * FROM {table}").fetchall() == before
        assert s.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (3,)
    finally:
        s.close()
        b.close()


def test_failed_decode_audited(tmp_path, monkeypatch):
    b = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    s = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        store = BronzeEventStore(b)
        store.initialize()
        e = BronzeEvent(
            "kite_websocket",
            "s",
            "r",
            datetime.now(UTC),
            b"x",
            "kite_ws_binary_payload",
            "live_provider",
        )
        store.append_batch((e,), batch_key="b", input_artifact=b"x", job_id="fixture")

        def fail(*args):
            raise RuntimeError("INJECTED")

        monkeypatch.setattr("nse_quant.data_platform.kite_silver.decode", fail)
        with pytest.raises(RuntimeError):
            normalize_variant(
                b,
                s,
                capture_event_id=e.capture_event_id,
                envelope_hash=e.envelope_hash,
                actor_id="test",
                code_revision="fixture",
                initialize=True,
            )
        target = name(s, "silver", "kite_frames")
        assert s.execute(f"SELECT count(*) FROM {target}").fetchone() == (0,)
        assert s.execute(
            "SELECT state FROM medallion_audit.job_events ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("FAILED",)
    finally:
        s.close()
        b.close()
