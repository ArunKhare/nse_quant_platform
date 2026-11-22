"""Real DuckDB SQL-contract tests using isolated, minimal operational tables."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from nse_quant.market_data.persisted_provider import (
    RECONSTRUCTION_VERSION,
    PersistedChainSnapshotProvider,
    PersistedSnapshotError,
)
from nse_quant.ops.data_quality import DataQualityChecker

NOW = datetime(2026, 1, 2, 6, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    conn = duckdb.connect(str(tmp_path / "reader.duckdb"))
    conn.execute("""CREATE TABLE option_chain_snapshots (
        ts TIMESTAMPTZ, run_id VARCHAR, underlying VARCHAR, spot DOUBLE,
        expiry_count INTEGER, quote_count INTEGER, complete BOOLEAN, completeness JSON)""")
    conn.execute("""CREATE TABLE option_stream (
        ts TIMESTAMPTZ, run_id VARCHAR, underlying VARCHAR, expiry DATE,
        instrument_token BIGINT, tradingsymbol VARCHAR, strike DOUBLE, option_type VARCHAR,
        lot_size INTEGER, spot DOUBLE, ltp DOUBLE, bid DOUBLE, ask DOUBLE, volume BIGINT,
        oi BIGINT, iv DOUBLE, delta DOUBLE, gamma DOUBLE, vega DOUBLE, theta DOUBLE, payload_json JSON)""")
    try:
        yield SimpleNamespace(conn=conn, settings=SimpleNamespace(runtime=SimpleNamespace(stale_seconds=300)))
    finally:
        conn.close()


def seed(store, *, run_id="a", ts=NOW, days=(7, 35, 60, 91), header=True, complete=True, payload=True):
    manifest = {}
    for index, day in enumerate(days):
        expiry = NOW.date() + timedelta(days=day)
        tick = {"instrument_token": index + 1,
                "exchange_ts": (ts - timedelta(seconds=2)).isoformat(),
                "trade_ts": (ts - timedelta(seconds=3)).isoformat(),
                "received_at": (ts - timedelta(seconds=1)).isoformat()} if payload else {}
        store.conn.execute("INSERT INTO option_stream VALUES (" + ",".join(["?"] * 21) + ")", [
            ts, run_id, "NIFTY", expiry, index + 1, f"NIFTY{day}CE", 25000, "CE", 75,
            25000, 100, 99, 101, 500, 1000, 0.2, 0.5, 0.001, 100, -10, json.dumps(tick),
        ])
        manifest[expiry.isoformat()] = {"quote_count": 1, "has_atm_iv": True, "has_greeks": True}
    if header:
        store.conn.execute("INSERT INTO option_chain_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           [ts, run_id, "NIFTY", 25000, len(days), len(days), complete, json.dumps(manifest)])


def reader(store):
    return PersistedChainSnapshotProvider(store, underlying="NIFTY", clock=lambda: NOW)


def test_empty(store):
    assert reader(store).get_chain_snapshots() == []
    with pytest.raises(ValueError, match="No complete"):
        reader(store).get_chain_snapshot()


def test_roundtrip_analytics_timestamps_and_combined_shape(store):
    seed(store)
    snapshots = reader(store).get_chain_snapshots()
    assert len(snapshots) == 1
    item = snapshots[0]
    assert len({q.instrument.expiry for q in item.quotes}) == 4
    assert item.run_id == "a" and item.ts == NOW
    assert item.expiry == NOW.date() + timedelta(days=7)
    assert item.reconstruction_version == RECONSTRUCTION_VERSION
    assert item.decision_eligibility_asserted is False
    for quote in item.quotes:
        assert (quote.iv, quote.delta, quote.gamma, quote.vega, quote.theta) == (0.2, 0.5, 0.001, 100, -10)
        assert quote.exchange_ts == NOW - timedelta(seconds=2)
        assert quote.trade_ts == NOW - timedelta(seconds=3)
        assert quote.received_at == NOW - timedelta(seconds=1)
    assert DataQualityChecker(300).assess(item, now=NOW).is_usable


def test_missing_timestamps_are_not_synthesized_and_fail_quality(store):
    seed(store, payload=False)
    item = reader(store).get_chain_snapshot()
    for quote in item.quotes:
        assert quote.exchange_ts is None and quote.trade_ts is None and quote.received_at is None
        assert set(item.timestamp_provenance[quote.instrument_token].values()) == {"missing"}
    report = DataQualityChecker(300).assess(item, now=NOW)
    assert not report.is_usable
    assert any(issue.startswith("missing_quote_timestamp:") for issue in report.issues)


def test_header_binds_exact_run_despite_same_timestamp_decoys(store):
    seed(store)
    seed(store, run_id="other", header=False)
    store.conn.execute("UPDATE option_stream SET ltp = 999 WHERE run_id = 'other'")
    item = reader(store).get_chain_snapshot()
    assert len(item.quotes) == 4 and all(q.ltp == 100 for q in item.quotes)


def test_deleted_selected_row_is_integrity_failure_not_older_fallback(store):
    seed(store, run_id="older", ts=NOW - timedelta(seconds=10))
    seed(store)
    store.conn.execute("DELETE FROM option_stream WHERE run_id = 'a' AND instrument_token = 1")
    with pytest.raises(PersistedSnapshotError, match="manifest_mismatch"):
        reader(store).get_chain_snapshots()


def test_legacy_fallback_is_run_bound(store):
    seed(store, header=False, run_id="a", days=(7,))
    seed(store, header=False, run_id="b", days=(35,))
    assert reader(store).get_chain_snapshots() == []


def test_legacy_fallback_roundtrip(store):
    seed(store, header=False)
    assert reader(store).get_chain_snapshot().run_id == "a"


def test_ambiguous_legacy_batch_is_rejected(store):
    seed(store, header=False)
    seed(store, header=False, run_id="b")
    with pytest.raises(PersistedSnapshotError, match="ambiguous_legacy_batch"):
        reader(store).get_chain_snapshots()


def test_latest_complete_policy_remains_not_latest_incomplete_override(store):
    seed(store, run_id="older", ts=NOW - timedelta(seconds=10))
    seed(store, complete=False)
    assert reader(store).get_chain_snapshot().run_id == "older"


def test_injected_clock_controls_the_actual_sql_freshness_cutoff(store):
    seed(store, ts=NOW - timedelta(seconds=301))
    assert reader(store).get_chain_snapshots() == []


def test_future_batch_is_rejected(store):
    seed(store, ts=NOW + timedelta(seconds=1))
    with pytest.raises(PersistedSnapshotError, match="future_timestamp"):
        reader(store).get_chain_snapshots()


def test_malformed_timestamp_is_rejected(store):
    seed(store)
    store.conn.execute("UPDATE option_stream SET payload_json = ? WHERE instrument_token = 1",
                       [json.dumps({"received_at": "2026-01-02T06:00:00"})])
    with pytest.raises(PersistedSnapshotError, match="timezone_required"):
        reader(store).get_chain_snapshots()


@pytest.mark.parametrize("missing", ["exchange_ts", "trade_ts", "received_at"])
def test_individual_missing_timestamp_stays_missing(store, missing):
    seed(store)
    payload = {name: NOW.isoformat() for name in ("exchange_ts", "trade_ts", "received_at") if name != missing}
    store.conn.execute("UPDATE option_stream SET payload_json = ?", [json.dumps(payload)])
    quote = reader(store).get_chain_snapshot().quotes[0]
    assert getattr(quote, missing) is None


def test_duplicate_tokens_are_rejected(store):
    seed(store)
    store.conn.execute("INSERT INTO option_stream SELECT * FROM option_stream WHERE instrument_token = 1")
    with pytest.raises(PersistedSnapshotError, match="duplicate_tokens"):
        reader(store).get_chain_snapshots()


def test_bad_json_object_is_rejected(store):
    seed(store)
    store.conn.execute("UPDATE option_stream SET payload_json = '[]'")
    with pytest.raises(PersistedSnapshotError, match="json_object_required"):
        reader(store).get_chain_snapshots()


def test_reader_works_on_read_only_connection(store):
    seed(store)
    path = store.conn.execute("PRAGMA database_list").fetchone()[2]
    store.conn.close()
    conn = duckdb.connect(path, read_only=True)
    try:
        read_store = SimpleNamespace(conn=conn, settings=store.settings)
        assert len(reader(read_store).get_chain_snapshot().quotes) == 4
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("DELETE FROM option_stream")
    finally:
        conn.close()
