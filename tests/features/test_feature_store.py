from datetime import UTC, datetime, timedelta

from nse_quant.core.models import MarketFeatures, MarketRegime
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
        regime=MarketRegime.RANGE,
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
    assert loaded.regime == MarketRegime.RANGE

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
