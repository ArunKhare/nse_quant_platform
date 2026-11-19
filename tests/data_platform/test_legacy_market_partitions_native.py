"""Real disposable legacy SQL -> partitioned native Bronze coverage tests.

Repository QA required; no substituted successful native producer/reader outputs.
"""

import json
from datetime import UTC, datetime

import duckdb
import pytest
from test_legacy_market_snapshot import legacy as legacy

from nse_quant.data_platform import legacy_market_partitions as codec
from nse_quant.data_platform import legacy_market_partitions_store as service
from nse_quant.data_platform import legacy_market_snapshot as old
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore


@pytest.fixture
def target(tmp_path):
    path = tmp_path / "bronze.duckdb"
    with duckdb.connect(str(path)) as conn:
        BronzeEventStore(conn).initialize()
        AuditLedger(conn).initialize()
    return path


def capture(path, table="spot_candles"):
    with duckdb.connect(str(path), read_only=True) as conn:
        return codec.capture_partitioned_legacy_table(conn, table=table, source_label="synthetic")


def build(legacy, target, table="spot_candles", **changes):
    args = dict(
        table=table,
        source_label="synthetic",
        expected_capture_id=capture(legacy, table).capture_id,
        imported_at=datetime(2026, 2, 1, tzinfo=UTC),
        actor_id="synthetic",
        code_revision="a" * 40,
    )
    args.update(changes)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(target)) as bronze,
    ):
        return service.preserve_partitioned_legacy_table(source, bronze, **args)


def read(target, result):
    with duckdb.connect(str(target), read_only=True) as conn:
        return service.read_partitioned_legacy_recording(
            conn,
            capture_id=result["capture_id"],
            table=result["table"],
            source_label=result["source_label"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )


def grow(legacy, count):
    with duckdb.connect(str(legacy)) as conn:
        table = service.name(conn, "main", "spot_candles")
        conn.execute(
            f"INSERT INTO {table} SELECT instrument_token+1000+i,symbol,interval,"
            f"ts,open,high,low,close,volume,oi FROM {table},range(?) r(i)",
            [count],
        )


@pytest.mark.parametrize("table", ["spot_candles", "option_stream"], ids=["candles", "options"])
def test_actual_native_recording_both_profiles(legacy, target, table):
    result = build(legacy, target, table)
    recording = read(target, result)
    assert recording.capture.row_count == 1
    assert recording.original_recording_verified is True
    assert recording.current_legacy_source_checked is False
    assert recording.decision_eligibility_asserted is False


def test_more_than_old_limit_without_changing_snapshot_v1(legacy, target):
    grow(legacy, 1000)
    with (
        duckdb.connect(str(legacy), read_only=True) as conn,
        pytest.raises(ValueError, match="ROW_BOUND"),
    ):
        old.capture_legacy_table(conn, table="spot_candles", source_label="synthetic")
    result = build(legacy, target)
    recording = read(target, result)
    assert recording.capture.row_count == 1001
    assert len(recording.capture.partitions) == 2
    manifest = json.loads(recording.capture.manifest)
    assert [p["first_ordinal"] for p in manifest["partitions"]] == [0, 1000]


def test_first_write_before_source_capture(legacy, target, monkeypatch):
    result = build(legacy, target)

    def forbidden(*args, **kwargs):
        raise AssertionError("native capture must not run")

    monkeypatch.setattr(codec, "capture_partitioned_legacy_table", forbidden)
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(target)) as bronze,
        pytest.raises(ValueError, match="FIRST_WRITE"),
    ):
        service.preserve_partitioned_legacy_table(
            source,
            bronze,
            table="spot_candles",
            source_label="synthetic",
            expected_capture_id=result["capture_id"],
            imported_at=datetime(2026, 2, 1, tzinfo=UTC),
            actor_id="synthetic",
            code_revision="a" * 40,
        )


def test_reviewed_pin_mismatch_retains_failed_original(legacy, target):
    with pytest.raises(ValueError, match="WHOLE_TABLE_CHANGED"):
        build(legacy, target, expected_capture_id="0" * 64)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(legacy, target, expected_capture_id="0" * 64)
    with duckdb.connect(str(target), read_only=True) as conn:
        table = service.name(conn, "bronze", "event_variants")
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


@pytest.mark.parametrize(
    "case",
    ["part-missing", "payload", "artifact", "audit", "batch"],
    ids=["part", "payload", "artifact", "audit", "batch"],
)
def test_native_original_corruption_blocks_complete_recording(legacy, target, case):
    grow(legacy, 1000)
    result = build(legacy, target)
    with duckdb.connect(str(target)) as conn:
        events = service.name(conn, "bronze", "event_variants")
        if case == "part-missing":
            conn.execute(f"DELETE FROM {events} WHERE source_record_id='part-0001'")
        elif case == "payload":
            conn.execute(
                f"UPDATE {events} SET payload='bad'::BLOB WHERE source_record_id='part-0000'"
            )
        elif case == "artifact":
            conn.execute(f"DELETE FROM {service.name(conn, 'bronze', 'input_artifacts')}")
        elif case == "audit":
            conn.execute(
                f"DELETE FROM {service.name(conn, 'medallion_audit', 'job_events')} "
                "WHERE state='SUCCEEDED'"
            )
        else:
            conn.execute(
                f"UPDATE {service.name(conn, 'bronze', 'ingest_batches')} "
                "SET input_events=input_events-1"
            )
    with pytest.raises(ValueError):
        read(target, result)


def test_final_audit_failure_cannot_be_adopted(legacy, target, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(legacy, target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        table = service.name(conn, "bronze", "event_variants")
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (2,)


def test_actual_domain_failure_keeps_no_partial_parts(legacy, target):
    with duckdb.connect(str(target)) as conn:
        conn.execute(f"DROP TABLE {service.name(conn, 'bronze', 'input_artifacts')}")
    with pytest.raises(duckdb.Error):
        build(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        table = service.name(conn, "bronze", "event_variants")
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_recording_not_current_source_assertion(legacy, target):
    result = build(legacy, target)
    with duckdb.connect(str(legacy)) as conn:
        table = service.name(conn, "main", "spot_candles")
        conn.execute(f"UPDATE {table} SET close=7")
    assert read(target, result).current_legacy_source_checked is False
    assert capture(legacy).capture_id != result["capture_id"]


def test_timezone_canonical_recording_fingerprint(legacy, target):
    result = build(legacy, target)
    with duckdb.connect(str(target), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        value = service.read_partitioned_legacy_recording(
            conn,
            capture_id=result["capture_id"],
            table=result["table"],
            source_label=result["source_label"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )
        assert value.capture.row_count == 1


def test_same_live_file_alias_refused_and_parent_usable(legacy):
    value = capture(legacy)
    with duckdb.connect(str(legacy), read_only=True) as source:
        alias = source.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.preserve_partitioned_legacy_table(
                    source,
                    alias,
                    table="spot_candles",
                    source_label="synthetic",
                    expected_capture_id=value.capture_id,
                    imported_at=datetime(2026, 2, 1, tzinfo=UTC),
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert source.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_native_and_current_legacy_revalidation_are_separate(legacy, target):
    result = build(legacy, target)
    args = dict(
        capture_id=result["capture_id"],
        table=result["table"],
        source_label=result["source_label"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(target), read_only=True) as bronze,
    ):
        checked = service.revalidate_partitioned_legacy_recording(source, bronze, **args)
        assert checked.current_legacy_source_checked is True
        assert checked.decision_eligibility_asserted is False
    with duckdb.connect(str(legacy)) as source:
        table = service.name(source, "main", "spot_candles")
        source.execute(f"UPDATE {table} SET close=9")
    assert read(target, result).original_recording_verified is True
    with (
        duckdb.connect(str(legacy), read_only=True) as source,
        duckdb.connect(str(target), read_only=True) as bronze,
        pytest.raises(ValueError, match="CURRENT_WHOLE"),
    ):
        service.revalidate_partitioned_legacy_recording(source, bronze, **args)
