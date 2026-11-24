"""Small temporary-DuckDB acceptance selection; no network or live capture."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import india_vix_recording as m
from nse_quant.market_data.india_vix_inputs import RawVixCapture

NOW = datetime(2026, 11, 20, 5, tzinfo=UTC)
OWNER = "fixture-owner"
REVISION = "a" * 40


def capture(price: Any = 18.5, age: int = 0) -> RawVixCapture:
    reference = json.dumps(dict(exchange="NSE", segment="INDICES", tradingsymbol="INDIA VIX", instrument_token=123))
    raw = json.dumps(
        {
            "NSE:INDIA VIX": dict(
                instrument_token=123, last_price=price, timestamp=(NOW - timedelta(seconds=age)).isoformat()
            )
        }
    )
    return RawVixCapture(
        "NSE:INDIA VIX",
        123,
        hashlib.sha256(reference.encode()).hexdigest(),
        reference,
        NOW,
        NOW,
        raw,
        hashlib.sha256(raw.encode()).hexdigest(),
    )


def preserve(path, value):
    with duckdb.connect(str(path)) as conn:
        m.initialize_vix_bronze(conn, writer_owner=OWNER)
        return m.preserve_vix_capture(
            conn,
            value,
            capture_session_id="session",
            source_record_id="request-1",
            writer_owner=OWNER,
            code_revision=REVISION,
        )


def promote(bp, sp, pins):
    with duckdb.connect(str(bp), read_only=True) as bronze:
        context, _ = m.observe_vix_bronze(bronze, pins=pins, as_of=NOW)
        with duckdb.connect(str(sp)) as silver:
            m.initialize_vix_silver(silver, writer_owner=OWNER)
            return m.persist_vix_silver(
                bronze,
                silver,
                pins=pins,
                as_of=NOW,
                expected_context_sha256=hashlib.sha256(context).hexdigest(),
                writer_owner=OWNER,
                code_revision=REVISION,
            )


def replay(bp, sp, revision):
    with duckdb.connect(str(bp), read_only=True) as bronze, duckdb.connect(str(sp), read_only=True) as silver:
        return m.replay_vix_silver(bronze, silver, revision_id=revision)


def test_valid_replay_and_both_exact_retries(tmp_path):
    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    first = preserve(bp, capture())
    retry = preserve(bp, capture())
    assert retry["receipt"].already_committed and retry["receipt"].exact_retries == 1
    assert retry["pins"] == first["pins"]
    revision = promote(bp, sp, first["pins"])["revision_id"]
    assert promote(bp, sp, first["pins"])["exact_retry"]
    result = replay(bp, sp, revision)
    assert result["quality_state"] == "valid_observation"
    assert result["observation"]["iv30"] == pytest.approx(0.185)
    assert result["observation"]["session_calendar_verified"] is False
    assert result["observation"]["iv30_source"] == "india_vix"
    assert result["observation"]["decision_eligibility_asserted"] is False


@pytest.mark.parametrize("problem", ["invalid", "stale", "hash", "reference", "json"])
def test_invalid_evidence_retained_but_not_valid(tmp_path, problem):
    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    value = capture(-1) if problem == "invalid" else capture(age=301 if problem == "stale" else 0)
    if problem == "hash":
        value = replace(value, payload_sha256="0" * 64)
    elif problem == "reference":
        value = replace(value, instrument_reference_sha256="0" * 64)
    elif problem == "json":
        value = replace(value, payload_json="{broken", payload_sha256=hashlib.sha256(b"{broken").hexdigest())
    pins = preserve(bp, value)["pins"]
    with duckdb.connect(str(bp), read_only=True) as bronze:
        assert m.read_vix_bronze(bronze, pins=pins) == value
    result = replay(bp, sp, promote(bp, sp, pins)["revision_id"])
    assert result["quality_state"] == "rejected" and result["observation"] is None
    assert result["decision_eligibility_asserted"] is False


def test_conflict_is_retained_and_blocks_original_replay(tmp_path):
    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    pins = preserve(bp, capture())["pins"]
    revision = promote(bp, sp, pins)["revision_id"]
    conflict = preserve(bp, capture(19))
    assert conflict["conflicted"] and conflict["pins"] is None
    assert conflict["receipt"].conflict_variants == 1
    with duckdb.connect(str(bp), read_only=True) as bronze:
        name = m.BronzeEventStore(bronze).object_name("event_variants")
        assert bronze.execute(f"SELECT count(*) FROM {name}").fetchone() == (2,)
        with pytest.raises(ValueError):
            m.read_vix_bronze(bronze, pins=pins)
    with pytest.raises(ValueError):
        replay(bp, sp, revision)


@pytest.mark.parametrize("target", ["payload", "envelope", "artifact", "audit", "record", "source_link"])
def test_tampering_fails(tmp_path, target):
    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    pins = preserve(bp, capture())["pins"]
    revision = promote(bp, sp, pins)["revision_id"]
    path = sp if target in {"record", "source_link"} else bp
    with duckdb.connect(str(path)) as conn:
        variants = m.BronzeEventStore(conn).object_name("event_variants")
        artifacts = m.BronzeEventStore(conn).object_name("input_artifacts")
        sql = {
            "payload": f"UPDATE {variants} SET payload=encode('{{}}')",
            "envelope": f"UPDATE {variants} SET envelope_json='{{}}'",
            "artifact": f"UPDATE {artifacts} SET artifact_bytes=encode('{{}}')",
            "audit": f"UPDATE {m.table(conn, 'medallion_audit.job_events')} SET state='FAILED' WHERE event_index=3",
            "record": f"UPDATE {m.table(conn, m.RECORDS)} SET record_bytes=encode('{{}}')",
            "source_link": f"UPDATE {m.table(conn, m.SETS)} SET context=encode('{{}}')",
        }[target]
        conn.execute(sql)
    with pytest.raises((ValueError, TypeError, KeyError)):
        replay(bp, sp, revision)


def test_replay_has_no_writes_or_network(tmp_path, monkeypatch):
    from nse_quant.market_data.india_vix_inputs import KiteIndiaVixProvider

    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    pins = preserve(bp, capture())["pins"]
    revision = promote(bp, sp, pins)["revision_id"]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (bp, sp)]

    def forbidden(*args, **kwargs):
        raise AssertionError("Operational action attempted during replay")

    monkeypatch.setattr(KiteIndiaVixProvider, "capture", forbidden)
    monkeypatch.setattr(m.AuditLedger, "plan_job", forbidden)
    monkeypatch.setattr(m.BronzeEventStore, "append_batch", forbidden)
    replay(bp, sp, revision)
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in (bp, sp)]
    with duckdb.connect(str(bp)) as conn, pytest.raises(ValueError, match="READONLY"):
        m.read_vix_bronze(conn, pins=pins)


def test_same_store_and_unreviewed_context_fail(tmp_path):
    bp, sp = tmp_path / "bronze.duckdb", tmp_path / "silver.duckdb"
    pins = preserve(bp, capture())["pins"]
    with duckdb.connect(str(bp), read_only=True) as bronze:
        with pytest.raises(ValueError, match="SEPARATE"):
            m.persist_vix_silver(
                bronze,
                bronze,
                pins=pins,
                as_of=NOW,
                expected_context_sha256="0" * 64,
                writer_owner=OWNER,
                code_revision=REVISION,
            )
        with duckdb.connect(str(sp)) as silver:
            m.initialize_vix_silver(silver, writer_owner=OWNER)
            with pytest.raises(ValueError, match="REVIEWED"):
                m.persist_vix_silver(
                    bronze,
                    silver,
                    pins=pins,
                    as_of=NOW,
                    expected_context_sha256="0" * 64,
                    writer_owner=OWNER,
                    code_revision=REVISION,
                )
            assert silver.execute("SELECT count(*) FROM medallion_audit.jobs").fetchone() == (0,)
