"""Actual synthetic legacy -> partition Bronze -> persisted Silver, no success doubles."""

import json

import duckdb
import pytest
from test_legacy_market_partitions_native import build as preserve
from test_legacy_market_partitions_native import grow, target
from test_legacy_market_snapshot import legacy as legacy

from nse_quant.data_platform import legacy_market_partition_silver as codec
from nse_quant.data_platform import legacy_market_partition_silver_store as service
from nse_quant.data_platform.audit import AuditLedger, JobState

bronze_target = target


@pytest.fixture
def pipeline(legacy, bronze_target, tmp_path):
    grow(legacy, 1000)
    result = preserve(legacy, bronze_target)
    pins = codec.PartitionBronzePins(
        result["capture_id"],
        result["table"],
        result["source_label"],
        result["recording_fingerprint"],
    )
    silver = tmp_path / "silver.duckdb"  # Deliberate real catalog/schema collision.
    with duckdb.connect(str(silver)) as conn:
        service.initialize_partition_silver(conn)
    return legacy, bronze_target, silver, pins


def build(pipeline, **changes):
    _legacy, bronze_path, silver_path, pins = pipeline
    args = dict(pins=pins, actor_id="synthetic", code_revision="a" * 40)
    args.update(changes)
    with (
        duckdb.connect(str(bronze_path), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as silver,
    ):
        return service.persist_partition_silver(bronze, silver, **args)


def read(pipeline, result, mode="retained"):
    legacy_path, bronze_path, silver_path, _pins = pipeline
    args = dict(
        revision_id=result["revision_id"],
        expected_recording_fingerprint=result["recording_fingerprint"],
    )
    with duckdb.connect(str(silver_path), read_only=True) as silver:
        if mode == "retained":
            return service.read_partition_silver(silver, **args)
        with duckdb.connect(str(bronze_path), read_only=True) as bronze:
            if mode == "bronze":
                return service.revalidate_partition_silver(bronze, silver, **args)
            with duckdb.connect(str(legacy_path), read_only=True) as source:
                return service.revalidate_partition_silver_source(source, bronze, silver, **args)


def test_native_complete_pipeline_all_three_read_modes(pipeline):
    result = build(pipeline)
    for mode in ("retained", "bronze", "source"):
        records = read(pipeline, result, mode)
        assert len(records) == result["row_count"] == 1001
        assert [json.loads(r)["source_ordinal"] for r in records] == list(range(1001))
        assert {json.loads(r)["partition_index"] for r in records} == {0, 1}
        assert json.loads(records[0])["stored_fields"]["open"] == (-0.0).hex()
        assert json.loads(records[0])["stored_fields"]["volume"] == "0"
        assert json.loads(records[0])["stored_fields"]["oi"] is None


def test_actual_option_producer(legacy, bronze_target, tmp_path):
    result = preserve(legacy, bronze_target, table="option_stream")
    pins = codec.PartitionBronzePins(
        result["capture_id"], "option_stream", "synthetic", result["recording_fingerprint"]
    )
    silver = tmp_path / "silver.duckdb"
    with duckdb.connect(str(silver)) as conn:
        service.initialize_partition_silver(conn)
    pipeline = legacy, bronze_target, silver, pins
    record = json.loads(read(pipeline, build(pipeline), "source")[0])
    assert record["legacy_derived_fields"]["iv"] == (0.2).hex()
    assert record["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "column,value",
    [
        ("partition_index", "2"),
        ("partition_ordinal", "9999"),
        ("partition_payload_sha256", "'bad'"),
        ("volume", "1"),
        ("capture_id", "'bad'"),
        ("record_bytes", "'bad'::BLOB"),
    ],
    ids=["part", "local", "hash", "volume", "capture", "bytes"],
)
def test_scalar_and_full_bytes_corruption(pipeline, column, value):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        conn.execute(f"UPDATE {records} SET {column}={value} WHERE ordinal=1000")
    with pytest.raises(ValueError, match="RECOMPUTATION"):
        read(pipeline, result)


@pytest.mark.parametrize(
    "case",
    ["missing", "attempt", "audit", "contract", "artifact"],
    ids=["missing", "attempt", "audit", "contract", "artifact"],
)
def test_coverage_and_original_obligations(pipeline, case):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        if case == "missing":
            conn.execute(f"DELETE FROM {records} WHERE partition_index=1")
        elif case == "attempt":
            conn.execute(f"DELETE FROM {service.name(conn, 'silver', 'partition_legacy_attempts')}")
        elif case == "audit":
            conn.execute(
                f"DELETE FROM {service.name(conn, 'medallion_audit', 'job_events')} "
                "WHERE state='SUCCEEDED'"
            )
        elif case == "contract":
            conn.execute(
                f"UPDATE {service.name(conn, 'medallion_audit', 'dataset_contracts')} "
                "SET fingerprint='bad'"
            )
        else:
            conn.execute(
                f"UPDATE {service.name(conn, 'silver', 'partition_legacy_sets')} "
                "SET source_artifact='bad'::BLOB"
            )
    with pytest.raises(ValueError):
        read(pipeline, result)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_unlinked_scoped_jobs_block_reader_and_writer(pipeline, state):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        ledger = AuditLedger(conn)
        job = ledger.plan_job(
            command_name=service.COMMAND,
            actor_id="synthetic",
            scope_ref="sha256:" + pipeline[3].scope_id,
            code_revision="a" * 40,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(pipeline, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_first_write_precedes_actual_reader(pipeline, monkeypatch):
    build(pipeline)

    def forbidden(*args, **kwargs):
        raise AssertionError("native source should not be read")

    monkeypatch.setattr(service.bronze_source, "read_partitioned_legacy_recording", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_actual_bronze_metadata_drift_failed_original_not_healed(pipeline):
    with duckdb.connect(str(pipeline[1])) as conn:
        events = service.name(conn, "bronze", "event_variants")
        conn.execute(f"UPDATE {events} SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError, match="FINGERPRINT"):
        build(pipeline)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_failed_second_source_observation_no_domain_adoption(pipeline, monkeypatch):
    original = service.bronze_source.read_partitioned_legacy_recording
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_READ")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.bronze_source, "read_partitioned_legacy_recording", fail_second)
    with pytest.raises(RuntimeError, match="SECOND_READ"):
        build(pipeline)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_domain_partial_insert_rollback_retains_failed_job(pipeline, monkeypatch):
    original = codec.record_values
    calls = 0

    def fail_second(raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_INSERT")
        return original(raw)

    monkeypatch.setattr(codec, "record_values", fail_second)
    with pytest.raises(RuntimeError, match="SECOND_INSERT"):
        build(pipeline)
    monkeypatch.setattr(codec, "record_values", original)
    with duckdb.connect(str(pipeline[2]), read_only=True) as conn:
        for table in (
            "partition_legacy_sets",
            "partition_legacy_observations",
            "partition_legacy_attempts",
        ):
            count = conn.execute(
                f"SELECT count(*) FROM {service.name(conn, 'silver', table)}"
            ).fetchone()
            assert count == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_final_audit_failure_retains_domain_but_cannot_be_read_or_healed(pipeline, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(pipeline)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(pipeline[2]), read_only=True) as conn:
        sets = service.name(conn, "silver", "partition_legacy_sets")
        row = conn.execute(f"SELECT revision_id,row_count FROM {sets}").fetchone()
        assert row is not None
        assert row[1] == 1001
        with pytest.raises(ValueError, match="AUDIT"):
            service.read_partition_silver(
                conn, revision_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_retained_bronze_current_source_are_distinct(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[0])) as conn:
        conn.execute(f"UPDATE {service.name(conn, 'main', 'spot_candles')} SET close=7")
    assert len(read(pipeline, result)) == len(read(pipeline, result, "bronze")) == 1001
    with pytest.raises(ValueError, match="CURRENT_WHOLE"):
        read(pipeline, result, "source")
    with duckdb.connect(str(pipeline[1])) as conn:
        conn.execute(
            f"DELETE FROM {service.name(conn, 'medallion_audit', 'job_events')} "
            "WHERE state='SUCCEEDED'"
        )
    assert len(read(pipeline, result)) == 1001
    with pytest.raises(ValueError, match="AUDIT"):
        read(pipeline, result, "bronze")


def test_timezone_and_wrong_recording_pin(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            len(
                service.read_partition_silver(
                    conn,
                    revision_id=result["revision_id"],
                    expected_recording_fingerprint=result["recording_fingerprint"],
                )
            )
            == 1001
        )
        with pytest.raises(ValueError, match="FINGERPRINT"):
            service.read_partition_silver(
                conn, revision_id=result["revision_id"], expected_recording_fingerprint="0" * 64
            )


def test_orphan_rows_block_before_source_read(pipeline, monkeypatch):
    build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        for schema, table in (
            ("silver", "partition_legacy_sets"),
            ("silver", "partition_legacy_attempts"),
            ("medallion_audit", "job_events"),
            ("medallion_audit", "jobs"),
        ):
            conn.execute(f"DELETE FROM {service.name(conn, schema, table)}")

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan source must not be read")

    monkeypatch.setattr(service.bronze_source, "read_partitioned_legacy_recording", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        build(pipeline)


def test_aggregate_sql_preflight_before_unbounded_transfer(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        conn.execute(
            f"UPDATE {records} SET record_bytes=encode(repeat('x',?)) WHERE ordinal=0",
            [codec.MAX_RECORD_TOTAL_BYTES + 1],
        )
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        read(pipeline, result)


def test_same_live_file_cursor_alias_parent_usable(pipeline):
    with duckdb.connect(str(pipeline[1]), read_only=True) as bronze:
        alias = bronze.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.persist_partition_silver(
                    bronze, alias, pins=pipeline[3], actor_id="synthetic", code_revision="a" * 40
                )
            assert bronze.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_no_reinitialization_or_legacy_profile_adoption(pipeline):
    with duckdb.connect(str(pipeline[2])) as conn, pytest.raises(ValueError, match="EMPTY"):
        service.initialize_partition_silver(conn)


def test_operational_source_sql_error_propagates(pipeline):
    with duckdb.connect(str(pipeline[1])) as conn:
        conn.execute(f"DROP TABLE {service.name(conn, 'bronze', 'event_variants')}")
    with pytest.raises(duckdb.Error):
        build(pipeline)


def test_extra_same_capture_revision_cannot_hide_outside_good_subset(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        conn.execute(
            f"INSERT INTO {records} SELECT ?,ordinal,partition_index,partition_ordinal,"
            "partition_payload_sha256,record_id,source_table,instrument_token,stored_ts,"
            f"volume,oi,record_bytes,source_observation_id,capture_id,recorded_at FROM {records} "
            "WHERE ordinal=0",
            ["0" * 64],
        )
    with pytest.raises(ValueError, match="COVERAGE"):
        read(pipeline, result)


def test_per_record_sql_transfer_bound(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        conn.execute(
            f"UPDATE {records} SET record_bytes=encode(repeat('x',?)) WHERE ordinal=0",
            [codec.MAX_RECORD_BYTES + 1],
        )
    with pytest.raises(ValueError, match="RECOMPUTATION"):
        read(pipeline, result)


def test_native_missing_partition_not_accepted_as_partial_silver(pipeline):
    with duckdb.connect(str(pipeline[1])) as conn:
        events = service.name(conn, "bronze", "event_variants")
        conn.execute(f"DELETE FROM {events} WHERE source_record_id='part-0001'")
    with pytest.raises(ValueError, match="COVERAGE"):
        build(pipeline)
    with duckdb.connect(str(pipeline[2]), read_only=True) as conn:
        sets = service.name(conn, "silver", "partition_legacy_sets")
        assert conn.execute(f"SELECT count(*) FROM {sets}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)


def test_reader_refuses_write_capable_handle(pipeline):
    result = build(pipeline)
    with duckdb.connect(str(pipeline[2])) as conn, pytest.raises(ValueError, match="READONLY"):
        service.read_partition_silver(
            conn,
            revision_id=result["revision_id"],
            expected_recording_fingerprint=result["recording_fingerprint"],
        )


def test_actual_domain_sql_failure_rolls_back_set_and_keeps_failed_obligation(pipeline):
    with duckdb.connect(str(pipeline[2])) as conn:
        records = service.name(conn, "silver", "partition_legacy_observations")
        conn.execute(f"ALTER TABLE {records} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        build(pipeline)
    with duckdb.connect(str(pipeline[2]), read_only=True) as conn:
        for table in (
            "partition_legacy_sets",
            "partition_legacy_observations",
            "partition_legacy_attempts",
        ):
            count = conn.execute(
                f"SELECT count(*) FROM {service.name(conn, 'silver', table)}"
            ).fetchone()
            assert count == (0,)
        history = service.name(conn, "medallion_audit", "job_events")
        assert conn.execute(
            f"SELECT state FROM {history} ORDER BY event_index DESC LIMIT 1"
        ).fetchone() == ("FAILED",)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(pipeline)
