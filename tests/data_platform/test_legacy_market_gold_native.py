"""Actual legacy -> partition Bronze -> Silver -> Gold, plus adversarial replay tests."""

import json
from dataclasses import replace
from typing import Any

import duckdb
import pytest
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import build as build_silver
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_market_partition_silver_native import pipeline as pipeline
from test_legacy_market_partitions_native import build as preserve

from nse_quant.data_platform import legacy_market_gold as codec
from nse_quant.data_platform import legacy_market_gold_store as service
from nse_quant.data_platform import legacy_market_partition_silver as silver_codec
from nse_quant.data_platform import legacy_market_partition_silver_store as silver_service
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def native(pipeline, tmp_path):
    result = build_silver(pipeline)
    pins = codec.GoldSourcePins(result["revision_id"], result["recording_fingerprint"])
    gold = tmp_path / "gold.duckdb"  # Real catalog/schema collision, not a renamed fixture.
    with duckdb.connect(str(gold)) as conn:
        service.initialize_legacy_price_gold(conn)
    return pipeline, gold, pins


def build(native, **changes):
    source_pipeline, gold_path, pins = native
    args = dict(pins=pins, actor_id="synthetic", code_revision="a" * 40)
    args.update(changes)
    with (
        duckdb.connect(str(source_pipeline[1]), read_only=True) as bronze,
        duckdb.connect(str(source_pipeline[2]), read_only=True) as silver,
        duckdb.connect(str(gold_path)) as gold,
    ):
        return service.persist_legacy_price_gold(bronze, silver, gold, **args)


def read(native, result, current=False):
    source_pipeline, gold_path, _pins = native
    args = dict(
        build_id=result["build_id"], expected_recording_fingerprint=result["recording_fingerprint"]
    )
    with duckdb.connect(str(gold_path), read_only=True) as gold:
        if not current:
            return service.read_legacy_price_gold(gold, **args)
        with (
            duckdb.connect(str(source_pipeline[1]), read_only=True) as bronze,
            duckdb.connect(str(source_pipeline[2]), read_only=True) as silver,
        ):
            return service.revalidate_legacy_price_gold(bronze, silver, gold, **args)


def test_actual_complete_native_1001_rows_and_partition_lineage(native):
    result = build(native)
    rows = read(native, result, current=True)
    assert len(rows) == result["row_count"] == 1001
    docs = [json.loads(r) for r in rows]
    assert [d["source_ordinal"] for d in docs] == list(range(1001))
    assert {d["partition_index"] for d in docs} == {0, 1}
    assert all(d["source_pins"]["revision_id"] == native[2].revision_id for d in docs)
    assert all(d["published_at"] is None for d in docs)
    assert all(d["decision_eligibility_asserted"] is False for d in docs)
    with duckdb.connect(str(native[1]), read_only=True) as conn:
        for table in ("legacy_price_inputs", "legacy_price_features"):
            assert conn.execute(
                f"SELECT count(*) FROM {service.name(conn, 'gold', table)}"
            ).fetchone() == (1001,)


def test_actual_option_source_recomputed_separately_from_legacy_iv(legacy, bronze_target, tmp_path):
    with duckdb.connect(str(legacy)) as conn:
        table = service.name(conn, "main", "option_stream")
        conn.execute(f"UPDATE {table} SET bid=10,ask=12,ltp=11.5,spot=101,strike=100")
    original = preserve(legacy, bronze_target, table="option_stream")
    bronze_pins = silver_codec.PartitionBronzePins(
        original["capture_id"], "option_stream", "synthetic", original["recording_fingerprint"]
    )
    silver_path = tmp_path / "options.duckdb"
    gold_path = tmp_path / "gold.duckdb"
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as silver,
    ):
        silver_service.initialize_partition_silver(silver)
        result = silver_service.persist_partition_silver(
            bronze, silver, pins=bronze_pins, actor_id="synthetic", code_revision="a" * 40
        )
    with duckdb.connect(str(gold_path)) as gold:
        service.initialize_legacy_price_gold(gold)
    pins = codec.GoldSourcePins(result["revision_id"], result["recording_fingerprint"])
    native = (legacy, bronze_target, silver_path, bronze_pins), gold_path, pins
    body = json.loads(read(native, build(native), current=True)[0])
    assert body["native_recomputed_features"]["ask_minus_bid"]["numerator"] == "2"
    assert body["native_recomputed_features"]["ltp_minus_midpoint"]["denominator"] == "2"
    assert body["retained_legacy_derived_fields"]["iv"] == (0.2).hex()
    assert "iv" not in body["native_recomputed_features"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("instrument_token", "0"),
        ("source_record_id", "'bad'"),
        ("feature_id", "'bad'"),
        ("feature_version", "'bad'"),
        ("feature_bytes", "'bad'::BLOB"),
        ("published_at", "current_timestamp"),
    ],
    ids=["token", "source", "id", "version", "bytes", "publication"],
)
def test_full_feature_scalar_and_byte_corruption(native, column, value):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        table = service.name(conn, "gold", "legacy_price_features")
        conn.execute(f"UPDATE {table} SET {column}={value} WHERE ordinal=1000")
    with pytest.raises(ValueError, match="RECOMPUTATION"):
        read(native, result)


@pytest.mark.parametrize(
    "case",
    ["input", "feature", "attempt", "audit", "contract", "runtime"],
    ids=["input", "feature", "attempt", "audit", "contract", "runtime"],
)
def test_original_coverage_and_recording_obligations(native, case):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        if case in ("input", "feature"):
            table = "legacy_price_inputs" if case == "input" else "legacy_price_features"
            conn.execute(f"DELETE FROM {service.name(conn, 'gold', table)} WHERE ordinal=1000")
        elif case == "attempt":
            conn.execute(f"DELETE FROM {service.name(conn, 'gold', 'legacy_price_attempts')}")
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
                f"UPDATE {service.name(conn, 'gold', 'legacy_price_builds')} "
                "SET runtime_pins='bad'::BLOB"
            )
    with pytest.raises(ValueError):
        read(native, result)


@pytest.mark.parametrize(
    "state",
    ["PLANNED", "RUNNING", "FAILED", "CANCELLED"],
    ids=["planned", "running", "failed", "cancelled"],
)
def test_unlinked_scoped_jobs_cannot_be_filtered(native, state):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        ledger = AuditLedger(conn)
        job = ledger.plan_job(
            command_name=service.COMMAND,
            actor_id="synthetic",
            scope_ref="sha256:" + native[2].scope_id,
            code_revision="a" * 40,
            config_hash="b" * 64,
        )
        if state != "PLANNED":
            ledger.transition(job, JobState(state))
    with pytest.raises(ValueError):
        read(native, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_first_write_blocks_before_native_reader(native, monkeypatch):
    build(native)

    def forbidden(*args, **kwargs):
        raise AssertionError("native source must not be read")

    monkeypatch.setattr(service.source, "revalidate_partition_silver", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_final_audit_failure_not_adoptable_or_readable(native, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(native)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(native[1]), read_only=True) as conn:
        table = service.name(conn, "gold", "legacy_price_builds")
        row = conn.execute(f"SELECT build_id,input_count FROM {table}").fetchone()
        assert row is not None and row[1] == 1001
        with pytest.raises(ValueError, match="AUDIT"):
            service.read_legacy_price_gold(
                conn, build_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_domain_partial_write_rollback_and_failed_obligation(native, monkeypatch):
    original = codec.feature_values
    calls = 0

    def fail(raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_ROW")
        return original(raw)

    monkeypatch.setattr(codec, "feature_values", fail)
    with pytest.raises(RuntimeError, match="SECOND_ROW"):
        build(native)
    monkeypatch.setattr(codec, "feature_values", original)
    assert_empty_domain(native)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def assert_empty_domain(native):
    with duckdb.connect(str(native[1]), read_only=True) as conn:
        for table in (
            "legacy_price_builds",
            "legacy_price_inputs",
            "legacy_price_features",
            "legacy_price_attempts",
        ):
            assert conn.execute(
                f"SELECT count(*) FROM {service.name(conn, 'gold', table)}"
            ).fetchone() == (0,)


def test_actual_domain_sql_failure_rolls_back_every_domain_table(native):
    with duckdb.connect(str(native[1])) as conn:
        table = service.name(conn, "gold", "legacy_price_features")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        build(native)
    assert_empty_domain(native)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_native_source_metadata_drift_failed_original_not_healed(native):
    with duckdb.connect(str(native[0][2])) as conn:
        table = service.name(conn, "silver", "partition_legacy_sets")
        conn.execute(f"UPDATE {table} SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError):
        build(native)
    assert_empty_domain(native)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_retained_gold_current_native_and_current_legacy_are_distinct(native):
    result = build(native)
    with duckdb.connect(str(native[0][0])) as conn:
        conn.execute(f"UPDATE {service.name(conn, 'main', 'spot_candles')} SET close=7")
    assert len(read(native, result, current=True)) == 1001
    with duckdb.connect(str(native[0][1])) as conn:
        table = service.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(native, result)) == 1001
    with pytest.raises(ValueError, match="AUDIT"):
        read(native, result, current=True)


@pytest.mark.parametrize(
    "table,column,limit",
    [
        ("legacy_price_inputs", "record_bytes", codec.MAX_INPUT_TOTAL_BYTES),
        ("legacy_price_features", "feature_bytes", codec.MAX_FEATURE_TOTAL_BYTES),
    ],
    ids=["inputs", "features"],
)
def test_sql_aggregate_transfer_preflight(native, table, column, limit):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        target = service.name(conn, "gold", table)
        conn.execute(
            f"UPDATE {target} SET {column}=encode(repeat('x',?)) WHERE ordinal=0", [limit + 1]
        )
    with pytest.raises(ValueError, match="AGGREGATE_BYTE_BOUND"):
        read(native, result)


@pytest.mark.parametrize(
    "table,column,limit",
    [
        ("legacy_price_inputs", "record_bytes", codec.MAX_INPUT_ROW_BYTES),
        ("legacy_price_features", "feature_bytes", codec.MAX_FEATURE_ROW_BYTES),
    ],
    ids=["inputs", "features"],
)
def test_sql_per_row_transfer_guard(native, table, column, limit):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        target = service.name(conn, "gold", table)
        conn.execute(
            f"UPDATE {target} SET {column}=encode(repeat('x',?)) WHERE ordinal=0", [limit + 1]
        )
    with pytest.raises(ValueError):
        read(native, result)


@pytest.mark.parametrize(
    "table",
    ["legacy_price_inputs", "legacy_price_features"],
    ids=["input-orphan", "feature-orphan"],
)
def test_orphan_rows_refuse_before_native_source_read(native, monkeypatch, table):
    build(native)
    with duckdb.connect(str(native[1])) as conn:
        for schema, name in (
            ("gold", "legacy_price_builds"),
            ("gold", "legacy_price_attempts"),
            ("medallion_audit", "job_events"),
            ("medallion_audit", "jobs"),
        ):
            conn.execute(f"DELETE FROM {service.name(conn, schema, name)}")
        other = "legacy_price_features" if table == "legacy_price_inputs" else "legacy_price_inputs"
        conn.execute(f"DELETE FROM {service.name(conn, 'gold', other)}")

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan source should not be read")

    monkeypatch.setattr(service.source, "revalidate_partition_silver", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        build(native)


def test_source_content_replay_rejects_reordered_or_promoted_rows(native):
    source_pipeline, _gold, pins = native
    with duckdb.connect(str(source_pipeline[2]), read_only=True) as silver:
        records = silver_service.read_partition_silver(silver, **pins.arguments())
    with pytest.raises(ValueError, match="REPLAY"):
        codec.derive_gold_records(tuple(reversed(records)), pins=pins)
    body = json.loads(records[0])
    body["decision_eligibility_asserted"] = True
    altered = (codec.canonical(body), *records[1:])
    with pytest.raises(ValueError, match="REPLAY"):
        codec.derive_gold_records(altered, pins=pins)


def test_bad_review_pin_cannot_create_adoptable_scope(native):
    changed = replace(native[2], recording_fingerprint="0" * 64)
    assert changed.scope_id == native[2].scope_id
    with pytest.raises(ValueError):
        build(native, pins=changed)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_timezone_and_separate_recording_pin(native):
    result = build(native)
    with duckdb.connect(str(native[1]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            len(
                service.read_legacy_price_gold(
                    conn,
                    build_id=result["build_id"],
                    expected_recording_fingerprint=result["recording_fingerprint"],
                )
            )
            == 1001
        )
        with pytest.raises(ValueError, match="FINGERPRINT"):
            service.read_legacy_price_gold(
                conn, build_id=result["build_id"], expected_recording_fingerprint="0" * 64
            )


def test_same_live_file_alias_refused_and_parent_usable(native):
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
    ):
        alias = silver.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                service.persist_legacy_price_gold(
                    bronze,
                    silver,
                    alias,
                    pins=native[2],
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert silver.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()


def test_no_reinitialization_and_no_writable_reader(native):
    result = build(native)
    with duckdb.connect(str(native[1])) as gold:
        with pytest.raises(ValueError, match="EMPTY"):
            service.initialize_legacy_price_gold(gold)
        with pytest.raises(ValueError, match="READONLY"):
            service.read_legacy_price_gold(
                gold,
                build_id=result["build_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )


@pytest.mark.parametrize("count", [0, 16001], ids=["empty", "overflow"])
def test_source_count_bound_before_decode(count):
    with pytest.raises(ValueError, match="ROW_BOUND"):
        codec.validate_source_records((b"{}",) * count)


def test_maximum_profile_content_recomputation_not_native_source_attestation():
    schema = silver_codec.snapshot.SCHEMAS["spot_candles"]
    names = tuple(n for n, _kind in schema)
    stored_rows = []
    for token in range(1, 16001):
        fields: dict[str, Any] = dict.fromkeys(names)
        fields.update(instrument_token=str(token), ts="2026-01-01T00:00:00+00:00", interval="1m")
        stored_rows.append(tuple(fields[n] for n in names))
    capture = silver_codec.partitions.make_partition_capture(
        table="spot_candles", source_label="synthetic", schema=schema, rows=tuple(stored_rows)
    )
    bronze_pins = silver_codec.PartitionBronzePins(
        capture.capture_id, "spot_candles", "synthetic", "c" * 64
    )
    records = silver_codec.derive_partition_records(capture.artifact, pins=bronze_pins)
    pins = codec.GoldSourcePins("a" * 64, "b" * 64)
    rows = codec.derive_gold_records(records, pins=pins)
    assert len(rows) == 16000
    assert json.loads(rows[-1])["source_ordinal"] == 15999
    assert sum(map(len, rows)) <= codec.MAX_FEATURE_TOTAL_BYTES


def test_failed_second_actual_native_observation_keeps_no_domain(native, monkeypatch):
    original = service.source.revalidate_partition_silver
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_NATIVE_OBSERVATION")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.source, "revalidate_partition_silver", fail_second)
    with pytest.raises(RuntimeError, match="SECOND_NATIVE"):
        build(native)
    assert_empty_domain(native)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(native)


def test_extra_same_source_build_rows_are_not_hidden_by_good_subset(native):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        inputs = service.name(conn, "gold", "legacy_price_inputs")
        conn.execute(
            f"INSERT INTO {inputs} SELECT ?,source_revision_id,ordinal,source_record_id,"
            f"record_bytes FROM {inputs} WHERE ordinal=0",
            ["0" * 64],
        )
    with pytest.raises(ValueError):
        read(native, result)


def test_source_operational_errors_propagate_without_policy_success(native):
    with duckdb.connect(str(native[0][1])) as conn:
        table = service.name(conn, "bronze", "event_variants")
        conn.execute(f"DROP TABLE {table}")
    with pytest.raises(duckdb.Error):
        build(native)
    assert_empty_domain(native)


def test_source_content_byte_bounds_before_json_decode():
    with pytest.raises(ValueError, match="ROW_BYTE_BOUND"):
        codec.validate_source_records((b"x" * (codec.MAX_INPUT_ROW_BYTES + 1),))
    full = b"x" * codec.MAX_INPUT_ROW_BYTES
    with pytest.raises(ValueError, match="TOTAL_BYTE_BOUND"):
        codec.validate_source_records((full,) * 65)


def test_changed_gold_recording_clock_requires_original_pin(native):
    result = build(native)
    with duckdb.connect(str(native[1])) as conn:
        for table in ("legacy_price_builds", "legacy_price_features"):
            target = service.name(conn, "gold", table)
            conn.execute(f"UPDATE {target} SET recorded_at=recorded_at+INTERVAL 1 SECOND")
    with pytest.raises(ValueError, match="FINGERPRINT"):
        read(native, result)


def test_actual_candle_geometry_recomputes_invalid_stored_range_without_repair(
    legacy,
    bronze_target,
    tmp_path,
):
    with duckdb.connect(str(legacy)) as conn:
        table = service.name(conn, "main", "spot_candles")
        conn.execute(f"UPDATE {table} SET open=10,high=7,low=9,close=12")
    original = preserve(legacy, bronze_target)
    bronze_pins = silver_codec.PartitionBronzePins(
        original["capture_id"], "spot_candles", "synthetic", original["recording_fingerprint"]
    )
    silver_path = tmp_path / "candle_silver.duckdb"
    gold_path = tmp_path / "gold.duckdb"
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(silver_path)) as silver,
    ):
        silver_service.initialize_partition_silver(silver)
        result = silver_service.persist_partition_silver(
            bronze, silver, pins=bronze_pins, actor_id="synthetic", code_revision="a" * 40
        )
    with duckdb.connect(str(gold_path)) as gold:
        service.initialize_legacy_price_gold(gold)
    pins = codec.GoldSourcePins(result["revision_id"], result["recording_fingerprint"])
    native = (legacy, bronze_target, silver_path, bronze_pins), gold_path, pins
    body = json.loads(read(native, build(native), current=True)[0])
    assert body["native_recomputed_features"]["high_minus_low"]["numerator"] == "-2"
    assert body["native_recomputed_features"]["upper_shadow"]["numerator"] == "-5"
    assert "INVERTED_HIGH_LOW" in body["quality_flags"]
    assert body["economic_validity_verified"] is False
