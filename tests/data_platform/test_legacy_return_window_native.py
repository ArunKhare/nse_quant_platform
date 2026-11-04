"""Actual retained legacy -> native returns -> policy-explicit window Gold integration."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from test_legacy_candle_returns_native import build as build_returns
from test_legacy_candle_returns_native import returns_target as returns_target
from test_legacy_market_gold_native import build as build_geometry
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy
from test_legacy_market_partitions_native import build as preserve

from nse_quant.data_platform import legacy_market_gold as gold_codec
from nse_quant.data_platform import legacy_market_partition_silver as silver_codec
from nse_quant.data_platform import legacy_market_partition_silver_store as silver_store
from nse_quant.data_platform import legacy_return_window_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState


@pytest.fixture
def window_target(returns_target, tmp_path):
    result = build_returns(returns_target)
    directory = tmp_path / "windows"
    directory.mkdir()
    target = directory / "gold.duckdb"  # Actual catalog/schema collision.
    with duckdb.connect(str(target)) as c:
        store.initialize_return_window_gold(c)
    pins = store.ReturnWindowPins(result["build_id"], result["recording_fingerprint"])
    return returns_target, target, pins, store.features.ReturnWindowPolicy(2, 60000000)


def build(target, **changes):
    return_target, path, pins, policy = target
    native = return_target[0]
    args = dict(pins=pins, policy=policy, actor_id="synthetic", code_revision="a" * 40)
    args.update(changes)
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as geometry,
        duckdb.connect(str(return_target[1]), read_only=True) as returns,
        duckdb.connect(str(path)) as output,
    ):
        return store.persist_return_window_gold(bronze, silver, geometry, returns, output, **args)


def read(target, result, current=False):
    return_target, path, _pins, _policy = target
    native = return_target[0]
    args = dict(
        build_id=result["build_id"], expected_recording_fingerprint=result["recording_fingerprint"]
    )
    with duckdb.connect(str(path), read_only=True) as output:
        if not current:
            return store.read_return_window_gold(output, **args)
        with (
            duckdb.connect(str(native[0][1]), read_only=True) as bronze,
            duckdb.connect(str(native[0][2]), read_only=True) as silver,
            duckdb.connect(str(native[1]), read_only=True) as geometry,
            duckdb.connect(str(return_target[1]), read_only=True) as returns,
        ):
            return store.revalidate_return_window_gold(
                bronze, silver, geometry, returns, output, **args
            )


def test_complete_1001_rows_all_source_ordinals_including_unavailable(window_target):
    result = build(window_target)
    rows = read(window_target, result, current=True)
    assert len(rows) == result["row_count"] == 1001
    docs = [json.loads(r) for r in rows]
    assert [d["source_ordinal"] for d in docs] == list(range(1001))
    assert {d["partition_index"] for d in docs} == {0, 1}
    assert all(not d["decision_eligibility_asserted"] for d in docs)
    assert all(d["published_at"] is None for d in docs)


def test_real_source_series_grid_gap_and_recovery(legacy, bronze_target, tmp_path):
    with duckdb.connect(str(legacy)) as c:
        table = store.name(c, "main", "spot_candles")
        c.execute(f"DELETE FROM {table}")
        at = datetime(2026, 1, 1, tzinfo=UTC)
        for minute, price in zip(
            [0, 1, 2, 10, 11, 12], [1.0, 2.0, 4.0, 8.0, 16.0, 32.0], strict=True
        ):
            c.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?)",
                [1, "S", "1m", at + timedelta(minutes=minute), None, None, None, price, 0, None],
            )
    original = preserve(legacy, bronze_target)
    bp = silver_codec.PartitionBronzePins(
        original["capture_id"], "spot_candles", "synthetic", original["recording_fingerprint"]
    )
    sp, gp, rp, wp = (tmp_path / f"{n}.duckdb" for n in ("silver", "geometry", "returns", "gold"))
    with (
        duckdb.connect(str(bronze_target), read_only=True) as bronze,
        duckdb.connect(str(sp)) as silver,
    ):
        silver_store.initialize_partition_silver(silver)
        sr = silver_store.persist_partition_silver(
            bronze, silver, pins=bp, actor_id="synthetic", code_revision="a" * 40
        )
    with duckdb.connect(str(gp)) as geometry:
        store.source.source.initialize_legacy_price_gold(geometry)
    old = (
        (legacy, bronze_target, sp, bp),
        gp,
        gold_codec.GoldSourcePins(sr["revision_id"], sr["recording_fingerprint"]),
    )
    gr = build_geometry(old)
    with duckdb.connect(str(rp)) as returns:
        store.source.initialize_candle_return_gold(returns)
    rt = old, rp, store.source.CandleReturnPins(gr["build_id"], gr["recording_fingerprint"])
    rr = build_returns(rt)
    with duckdb.connect(str(wp)) as output:
        store.initialize_return_window_gold(output)
    target = (
        rt,
        wp,
        store.ReturnWindowPins(rr["build_id"], rr["recording_fingerprint"]),
        store.features.ReturnWindowPolicy(2, 60000000),
    )
    rows = [json.loads(r) for r in read(target, build(target), current=True)]
    assert rows[2]["values"]["sum_squared_simple_returns"] == dict(numerator="2", denominator="1")
    assert rows[3]["values"]["status"] == "UNAVAILABLE"
    assert rows[4]["values"]["status"] == "UNAVAILABLE"
    assert rows[5]["values"]["status"] == "COMPUTED_RESEARCH_WINDOW"
    assert not rows[5]["values"]["authoritative_market_coverage_verified"]


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("return_window_inputs", "record_bytes", "'bad'::BLOB"),
        ("return_window_outputs", "record_bytes", "'bad'::BLOB"),
        ("return_window_outputs", "record_id", "'bad'"),
        ("return_window_outputs", "published_at", "current_timestamp"),
        ("return_window_outputs", "feature_version", "'bad'"),
    ],
    ids=["input", "output", "hash", "publication", "version"],
)
def test_full_content_materialized_scalar_corruption(window_target, table, column, value):
    result = build(window_target)
    with duckdb.connect(str(window_target[1])) as c:
        qualified = store.name(c, "gold", table)
        c.execute(f"UPDATE {qualified} SET {column}={value} WHERE ordinal=0")
    with pytest.raises(ValueError):
        read(window_target, result)


@pytest.mark.parametrize(
    "case",
    ["row", "link", "audit", "definition", "policy"],
    ids=["row", "link", "audit", "definition", "policy"],
)
def test_original_obligations_and_policy_drift(window_target, case):
    result = build(window_target)
    with duckdb.connect(str(window_target[1])) as c:
        if case == "row":
            table = store.name(c, "gold", store.DOMAIN[3])
            c.execute(f"DELETE FROM {table} WHERE ordinal=1000")
        elif case == "link":
            c.execute(f"DELETE FROM {store.name(c, 'gold', store.DOMAIN[4])}")
        elif case == "audit":
            table = store.name(c, "medallion_audit", "job_events")
            c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
        elif case == "definition":
            table = store.name(c, "gold", store.DOMAIN[0])
            c.execute(f"UPDATE {table} SET definition='bad'::BLOB")
        else:
            table = store.name(c, "gold", store.DOMAIN[1])
            c.execute(
                f"UPDATE {table} SET policy=?",
                [store.canonical(dict(window_returns=3, cadence_microseconds=60000000))],
            )
    with pytest.raises(ValueError):
        read(window_target, result)


def test_recording_pin_does_not_heal_failed_scope(window_target):
    pins = replace(window_target[2], recording_fingerprint="0" * 64)
    assert store.scope_id(pins, window_target[3]) == store.scope_id(
        window_target[2], window_target[3]
    )
    with pytest.raises(ValueError):
        build(window_target, pins=pins)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


def test_distinct_reviewed_policy_is_a_distinct_build(window_target):
    one = build(window_target)
    two = build(window_target, policy=store.features.ReturnWindowPolicy(3, 60000000))
    assert one["build_id"] != two["build_id"]
    assert len(read(window_target, one)) == len(read(window_target, two)) == 1001


def test_extra_scoped_failure_cannot_hide(window_target):
    result = build(window_target)
    with duckdb.connect(str(window_target[1])) as c:
        ledger = AuditLedger(c)
        scope = store.scope_id(window_target[2], window_target[3])
        job = ledger.plan_job(
            command_name=store.COMMAND,
            actor_id="synthetic",
            code_revision="a" * 40,
            scope_ref="sha256:" + scope,
            config_hash="b" * 64,
        )
        ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    with pytest.raises(ValueError):
        read(window_target, result)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


def test_final_audit_failure_post_domain_cannot_adopt(window_target, monkeypatch):
    original = AuditLedger.transition

    def fail(self, job, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT")
        return original(self, job, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="FINAL_AUDIT"):
        build(window_target)
    monkeypatch.setattr(AuditLedger, "transition", original)
    with duckdb.connect(str(window_target[1]), read_only=True) as c:
        table = store.name(c, "gold", store.DOMAIN[1])
        row = c.execute(f"SELECT build_id FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(ValueError, match="AUDIT"):
            store.read_return_window_gold(
                c, build_id=row[0], expected_recording_fingerprint="a" * 64
            )
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


def test_actual_sql_domain_failure_rolls_back_all_rows(window_target):
    with duckdb.connect(str(window_target[1])) as c:
        table = store.name(c, "gold", store.DOMAIN[3])
        c.execute(f"ALTER TABLE {table} ADD COLUMN synthetic_failure INTEGER DEFAULT 0")
    with pytest.raises(duckdb.Error):
        build(window_target)
    with duckdb.connect(str(window_target[1]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            assert c.execute(f"SELECT count(*) FROM {store.name(c, 'gold', n)}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


@pytest.mark.parametrize(
    "table,limit,code",
    [
        ("return_window_inputs", 33554432, "AGGREGATE_BYTE_BOUND"),
        ("return_window_outputs", 33554432, "AGGREGATE_BYTE_BOUND"),
        ("return_window_inputs", 524288, "PER_ROW_BYTE_BOUND"),
        ("return_window_outputs", 65536, "PER_ROW_BYTE_BOUND"),
    ],
    ids=["inputs-total", "outputs-total", "input-cell", "output-cell"],
)
def test_independent_sql_resource_bounds(window_target, table, limit, code):
    result = build(window_target)
    with duckdb.connect(str(window_target[1])) as c:
        qualified = store.name(c, "gold", table)
        c.execute(
            f"UPDATE {qualified} SET record_bytes=encode(repeat('x',?)) WHERE ordinal=0",
            [limit + 1],
        )
    with pytest.raises(ValueError, match=code):
        read(window_target, result)


def test_retained_current_native_and_current_legacy_remain_distinct(window_target):
    result = build(window_target)
    native = window_target[0][0]
    with duckdb.connect(str(native[0][0])) as c:
        c.execute(f"UPDATE {store.name(c, 'main', 'spot_candles')} SET close=7")
    assert len(read(window_target, result, current=True)) == 1001
    with duckdb.connect(str(window_target[0][1])) as c:
        table = store.name(c, "medallion_audit", "job_events")
        c.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert len(read(window_target, result)) == 1001
    with pytest.raises(ValueError):
        read(window_target, result, current=True)


def test_first_write_before_actual_source(window_target, monkeypatch):
    build(window_target)

    def forbidden(*args, **kwargs):
        raise AssertionError("source must not be called")

    monkeypatch.setattr(store.source, "revalidate_candle_return_gold", forbidden)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


def test_timezone_original_pin_and_readonly(window_target):
    result = build(window_target)
    args = dict(
        build_id=result["build_id"], expected_recording_fingerprint=result["recording_fingerprint"]
    )
    with duckdb.connect(str(window_target[1]), read_only=True) as c:
        c.execute("SET TimeZone='Asia/Kolkata'")
        assert len(store.read_return_window_gold(c, **args)) == 1001
    with duckdb.connect(str(window_target[1])) as c:
        with pytest.raises(ValueError, match="READONLY"):
            store.read_return_window_gold(c, **args)
        with pytest.raises(ValueError, match="EMPTY"):
            store.initialize_return_window_gold(c)


def test_second_actual_source_failure_no_partial_window_build(window_target, monkeypatch):
    original = store.source.revalidate_candle_return_gold
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_WINDOW_SOURCE_READ")
        return original(*args, **kwargs)

    monkeypatch.setattr(store.source, "revalidate_candle_return_gold", observe)
    with pytest.raises(RuntimeError, match="SECOND_WINDOW_SOURCE_READ"):
        build(window_target)
    with duckdb.connect(str(window_target[1]), read_only=True) as c:
        for n in store.DOMAIN[1:]:
            table = store.name(c, "gold", n)
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    with pytest.raises(ValueError, match="FIRST_WRITE"):
        build(window_target)


def test_orphan_scope_rows_cannot_be_adopted(window_target, monkeypatch):
    build(window_target)
    with duckdb.connect(str(window_target[1])) as c:
        for schema, n in (
            ("gold", store.DOMAIN[1]),
            ("gold", store.DOMAIN[4]),
            ("medallion_audit", "jobs"),
            ("medallion_audit", "job_events"),
        ):
            c.execute(f"DELETE FROM {store.name(c, schema, n)}")

    def forbidden(*args, **kwargs):
        raise AssertionError("orphan must refuse before source")

    monkeypatch.setattr(store.source, "revalidate_candle_return_gold", forbidden)
    with pytest.raises(ValueError, match="ORPHAN"):
        build(window_target)


def test_same_live_file_alias_preserves_parent(window_target):
    with duckdb.connect(str(window_target[1])) as c:
        alias = c.cursor()
        try:
            with pytest.raises(ValueError, match="SEPARATE"):
                store.persist_return_window_gold(
                    c,
                    None,
                    None,
                    None,
                    alias,
                    pins=window_target[2],
                    policy=window_target[3],
                    actor_id="synthetic",
                    code_revision="a" * 40,
                )
            assert c.execute("SELECT 1").fetchone() == (1,)
        finally:
            alias.close()
