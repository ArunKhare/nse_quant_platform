from datetime import UTC, datetime, timedelta

from nse_quant.core.models import MarketFeatures, IntradayShape
from nse_quant.features.feature_store import FeatureStore
from nse_quant.persistence.duckdb_store import DuckDBStore


def make_features(ts: datetime, iv: float) -> MarketFeatures:
    return MarketFeatures(
        ts=ts,
        underlying="NIFTY",
        expiry=ts.date() + timedelta(days=7),
        spot=25000.0,
        atm_iv=iv,
        iv_rank=50.0,
        iv_percentile=60.0,
        realized_vol=12.0,
        intraday_shape=IntradayShape.RANGE,
    )


def test_feature_store_persists_and_reads(tmp_path):
    store = DuckDBStore(tmp_path / "test.duckdb")
    feature_store = FeatureStore(store.conn)

    base = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)
    features = make_features(base, 15.0)
    feature_store.save("run-1", features)

    loaded = feature_store.latest("NIFTY")

    assert loaded is not None
    assert loaded.atm_iv == 15.0
    assert loaded.iv_rank == 50.0
    assert loaded.intraday_shape == IntradayShape.RANGE

    store.close()


def test_iv_history_orders_values(tmp_path):
    store = DuckDBStore(tmp_path / "test.duckdb")

    store.conn.execute(
        """
        INSERT INTO option_stream VALUES (
            'run', '2026-10-16 10:00:00+00', 'NIFTY', '2026-10-23',
            25000, 'CE', 'NIFTY26OCT25000CE', 1, 75, 25000,
            100, 99, 101, 1000, 10000, 14, NULL, NULL, NULL, NULL,
            'ready', '{}'
        )
        """
    )

    store.conn.execute(
        """
        INSERT INTO option_stream VALUES (
            'run', '2026-10-16 10:01:00+00', 'NIFTY', '2026-10-23',
            25000, 'CE', 'NIFTY26OCT25000CE', 1, 75, 25000,
            100, 99, 101, 1000, 10000, 18, NULL, NULL, NULL, NULL,
            'ready', '{}'
        )
        """
    )

    history = store.latest_iv_history("NIFTY")

    assert history == [14.0, 18.0]
    store.close()



def _legacy_feature_store(tmp_path):
    conn = duckdb.connect(str(tmp_path / "legacy-features.duckdb"))
    columns = ", ".join(f'"{name}" {kind}' for name, kind in legacy_codec.SCHEMA)
    conn.execute(f"CREATE TABLE feature_snapshots ({columns}, PRIMARY KEY (feature_id))")
    return conn, FeatureStore(conn)


def test_legacy_latest_and_history_return_unknown_without_shape_column(tmp_path):
    conn, feature_store = _legacy_feature_store(tmp_path)
    try:
        ts = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)
        feature_store.save("legacy-run", make_features(ts, 15.0))
        conn.execute("UPDATE feature_snapshots SET regime = 'BULL|NORMAL'")

        latest = feature_store.latest("NIFTY")
        history = feature_store.history("NIFTY")

        assert latest is not None
        assert latest.intraday_shape == IntradayShape.UNKNOWN
        assert len(history) == 1
        assert history[0].intraday_shape == IntradayShape.UNKNOWN
        assert conn.execute("SELECT regime FROM feature_snapshots").fetchone() == ("BULL|NORMAL",)
    finally:
        conn.close()


def test_schema_migration_does_not_backfill_intraday_shape_from_regime(tmp_path):
    path = tmp_path / "legacy-migration.duckdb"
    conn = duckdb.connect(str(path))
    columns = ", ".join(f'"{name}" {kind}' for name, kind in legacy_codec.SCHEMA)
    conn.execute(f"CREATE TABLE feature_snapshots ({columns}, PRIMARY KEY (feature_id))")
    feature_store = FeatureStore(conn)
    feature_store.save("legacy-run", make_features(datetime(2026, 10, 16, 10, 0, tzinfo=UTC), 15.0))
    conn.execute("UPDATE feature_snapshots SET regime = 'BULL|NORMAL'")
    conn.close()

    store = DuckDBStore(path)
    try:
        regime, intraday_shape = store.conn.execute(
            "SELECT regime, intraday_shape FROM feature_snapshots"
        ).fetchone()
        assert regime == "BULL|NORMAL"
        assert intraday_shape is None
        loaded = FeatureStore(store.conn).latest("NIFTY")
        assert loaded is not None
        assert loaded.intraday_shape == IntradayShape.UNKNOWN
    finally:
        store.close()
