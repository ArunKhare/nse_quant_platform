"""Actual legacy -> partition Bronze -> Silver -> Gold -> candle-return Gold."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from test_legacy_market_gold_native import build as geometry
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_market_partitions_native import build as preserve

from nse_quant.data_platform import legacy_candle_returns_store as store
from nse_quant.data_platform import legacy_market_gold as gold_codec
from nse_quant.data_platform import legacy_market_partition_silver as silver_codec
from nse_quant.data_platform import legacy_market_partition_silver_store as silver_store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def returns_target(native, tmp_path):
    result = geometry(native)
    directory = tmp_path / "returns"
    directory.mkdir()
    path = directory / "gold.duckdb"  # Actual catalog/schema collision.
    with duckdb.connect(str(path)) as conn:
        store.initialize_candle_return_gold(conn)
    return native, path, store.CandleReturnPins(result["build_id"], result["recording_fingerprint"])


def build(target, **changes):
    native, path, pins = target
    args = dict(pins=pins, actor_id="synthetic", code_revision="a" * 40)
    args.update(changes)
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as gold,
        duckdb.connect(str(path)) as output,
    ):
        return store.persist_candle_return_gold(bronze, silver, gold, output, **args)


def read(target, result, current=False):
    native, path, _pins = target
    args = dict(
        build_id=result["build_id"], expected_recording_fingerprint=result["recording_fingerprint"]
    )
    with duckdb.connect(str(path), read_only=True) as output:
        if not current:
            return store.read_candle_return_gold(output, **args)
        with (
            duckdb.connect(str(native[0][1]), read_only=True) as bronze,
            duckdb.connect(str(native[0][2]), read_only=True) as silver,
            duckdb.connect(str(native[1]), read_only=True) as gold,
        ):
            return store.revalidate_candle_return_gold(bronze, silver, gold, output, **args)


def test_actual_complete_1001_row_partition_coverage(returns_target):
    result = build(returns_target)
    rows = read(returns_target, result, current=True)
    assert len(rows) == result["row_count"] == 1001
    docs = [json.loads(r) for r in rows]
    assert [r["source_ordinal"] for r in docs] == list(range(1001))
    assert {r["partition_index"] for r in docs} == {0, 1}
    assert all(not r["decision_eligibility_asserted"] for r in docs)
    assert all(r["published_at"] is None for r in docs)


def test_actual_chronological_series_and_missing_no_bridge(legacy, bronze_target, tmp_path):
    with duckdb.connect(str(legacy)) as conn:
        table = store.name(conn, "main", "spot_candles")
        conn.execute(f"DELETE FROM {table}")
        at = datetime(2026, 1, 1, tzinfo=UTC)
        for i, close in enumerate([10.0, 20.0, None, 30.0, 0.0, 40.0]):
            conn.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)",
                [1, "S", "1m", at + timedelta(minutes=i), None, None, None, close, 0, None],
            )
    preserved = preserve(legacy, bronze_target)
    bp = silver_codec.PartitionBronzePins(
        preserved["capture_id"], "spot_candles", "synthetic", preserved["recording_fingerprint"]
    )
    sp = tmp_path / "series_silver.duckdb"
    gp = tmp_path / "series_gold.duckdb"
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(sp)) as silver,
    ):
        silver_store.initialize_partition_silver(silver)
        sr = silver_store.persist_partition_silver(
            bronze, silver, pins=bp, actor_id="synthetic", code_revision="a" * 40
        )
    with duckdb.connect(str(gp)) as gold:
        store.source.initialize_legacy_price_gold(gold)
    original = (
        (legacy, bronze_target, sp, bp),
        gp,
        gold_codec.GoldSourcePins(sr["revision_id"], sr["recording_fingerprint"]),
    )
    gr = geometry(original)
    path = tmp_path / "gold.duckdb"
    with duckdb.connect(str(path)) as output:
        store.initialize_candle_return_gold(output)
    target = original, path, store.CandleReturnPins(gr["build_id"], gr["recording_fingerprint"])
    docs = [json.loads(r) for r in read(target, build(target), current=True)]
    assert docs[1]["values"]["simple_return"] == dict(numerator="1", denominator="1")
    assert docs[2]["values"]["simple_return"] is None
    assert docs[3]["values"]["simple_return"] is None
    assert docs[3]["values"]["predecessor_ordinal"] == 2
    assert docs[5]["values"]["simple_return"] is None


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("legacy_return_inputs", "record_bytes", "'bad'::BLOB"),
        ("legacy_return_outputs", "record_bytes", "'bad'::BLOB"),
        ("legacy_return_outputs", "record_id", "'bad'"),
        ("legacy_return_outputs", "published_at", "current_timestamp"),
        ("legacy_return_outputs", "feature_version", "'bad'"),
    ],
    ids=["input", "output", "hash", "publication", "version"],
)
def test_full_content_and_scalar_corruption(returns_target, table, column, value):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        qualified = store.name(conn, "gold", table)
        conn.execute(f"UPDATE {qualified} SET {column}={value} WHERE ordinal=0")
    with pytest.raises(ValueError):
        read(returns_target, result)


@pytest.mark.parametrize(
    "case",
    ["row", "link", "audit", "contract", "definition"],
    ids=["row", "link", "audit", "contract", "definition"],
)
def test_original_complete_obligations(returns_target, case):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        if case == "row":
            table = store.name(conn, "gold", store.DOMAIN[3])
            conn.execute(f"DELETE FROM {table} WHERE ordinal=1000")
        elif case == "link":
            conn.execute(f"DELETE FROM {store.name(conn, 'gold', store.DOMAIN[4])}")
        elif case == "audit":
            table = store.name(conn, "medallion_audit", "job_events")
            conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "contract":
            table = store.name(conn, "medallion_audit", "dataset_contracts")
            conn.execute(f"UPDATE {table} SET fingerprint='bad'")
        else:
            table = store.name(conn, "gold", store.DOMAIN[0])
            conn.execute(f"UPDATE {table} SET definition='bad'::BLOB")
    with pytest.raises(ValueError):
        read(returns_target, result)


def test_wrong_recording_pin_cannot_heal_scope(returns_target):
    bad = replace(returns_target[2], recording_fingerprint="0" * 64)
    assert bad.scope_id == returns_target[2].scope_id
    with pytest.raises(ValueError):
        build(returns_target, pins=bad)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)


def test_extra_scoped_job_blocks_good_subset(returns_target):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        ledger = AuditLedger(conn)
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            config_hash="b" * 64,
            scope_ref="sha256:" + returns_target[2].scope_id,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(ValueError):
        read(returns_target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)


def test_final_audit_failure_blocks_retained_read_and_adoption(returns_target, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(returns_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(returns_target[1]), read_only=True) as conn:
        table = store.name(conn, "gold", store.DOMAIN[1])
        row = conn.execute(f"SELECT build_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT"):
            store.read_candle_return_gold(
                conn, build_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)


def test_domain_sql_failure_rolls_back_all_build_rows(returns_target):
    with duckdb.connect(str(returns_target[1])) as conn:
        table = store.name(conn, "gold", store.DOMAIN[3])
        conn.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        build(returns_target)
    with duckdb.connect(str(returns_target[1]), read_only=True) as conn:
        for n in store.DOMAIN[1:]:
            table = store.name(conn, "gold", n)
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)


@pytest.mark.parametrize(
    "table,limit",
    [
        ("legacy_return_inputs", 33554432),
        ("legacy_return_outputs", 33554432),
    ],
    ids=["inputs", "outputs"],
)
def test_aggregate_sql_preflight(returns_target, table, limit):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        conn.execute(
            f"UPDATE {store.name(conn, 'gold', table)} "
            "SET record_bytes=encode(repeat('x',?)) WHERE ordinal=0",
            [limit + 1],
        )
    with pytest.raises(ValueError, match="AGGREGATE_BYTE_BOUND"):
        read(returns_target, result)


def test_retained_native_and_current_legacy_are_distinct(returns_target):
    result = build(returns_target)
    native = returns_target[0]
    with duckdb.connect(str(native[0][0])) as conn:
        conn.execute(f"UPDATE {store.name(conn, 'main', 'spot_candles')} SET close=7")
    assert len(read(returns_target, result, current=True)) == 1001
    with duckdb.connect(str(native[0][1])) as conn:
        table = store.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(returns_target, result)) == 1001
    with pytest.raises(ValueError):
        read(returns_target, result, current=True)


def test_timezone_readonly_and_no_reinitialization(returns_target):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1]), read_only=True) as conn:
        conn.execute("SET TimeZone='Asia/Kolkata'")
        assert (
            len(
                store.read_candle_return_gold(
                    conn,
                    build_id=result["build_id"],
                    expected_recording_fingerprint=result["recording_fingerprint"],
                )
            )
            == 1001
        )
    with duckdb.connect(str(returns_target[1])) as conn:
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_candle_return_gold(conn)
        with pytest.raises(ValueError, match="READONLY"):
            store.read_candle_return_gold(
                conn,
                build_id=result["build_id"],
                expected_recording_fingerprint=result["recording_fingerprint"],
            )


@pytest.mark.parametrize(
    "table,limit",
    [
        ("legacy_return_inputs", 524288),
        ("legacy_return_outputs", 65536),
    ],
    ids=["input-cell", "output-cell"],
)
def test_independent_per_row_guard(returns_target, table, limit):
    result = build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        qualified = store.name(conn, "gold", table)
        conn.execute(
            f"UPDATE {qualified} SET record_bytes=encode(repeat('x',?)) WHERE ordinal=0",
            [limit + 1],
        )
    with pytest.raises(ValueError, match="PER_ROW_BYTE_BOUND"):
        read(returns_target, result)


def test_first_write_precedes_actual_upstream(returns_target, monkeypatch):
    build(returns_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("upstream should not be called")

    monkeypatch.setattr(store.source, "revalidate_legacy_price_gold", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)


def test_orphan_complete_source_rows_cannot_be_adopted(returns_target, monkeypatch):
    build(returns_target)
    with duckdb.connect(str(returns_target[1])) as conn:
        for schema, table in (
            ("gold", store.DOMAIN[1]),
            ("gold", store.DOMAIN[4]),
            ("medallion_audit", "jobs"),
            ("medallion_audit", "job_events"),
        ):
            conn.execute(f"DELETE FROM {store.name(conn, schema, table)}")

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan must refuse before source")

    monkeypatch.setattr(store.source, "revalidate_legacy_price_gold", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        build(returns_target)


def test_second_actual_native_observation_failure_no_partial_build(returns_target, monkeypatch):
    original = store.source.revalidate_legacy_price_gold
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_NATIVE_READ")
        return original(*args, **kwargs)

    monkeypatch.setattr(store.source, "revalidate_legacy_price_gold", observe)
    with pytest.raises(RuntimeError, match="SECOND_NATIVE_READ"):
        build(returns_target)
    with duckdb.connect(str(returns_target[1]), read_only=True) as conn:
        for n in store.DOMAIN[1:]:
            assert conn.execute(
                f"SELECT count(*) FROM {store.name(conn, 'gold', n)}"
            ).fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(returns_target)
