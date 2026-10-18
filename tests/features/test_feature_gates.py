from datetime import UTC

import pandas as pd

from nse_quant.features.feature_gates import SpotFeatureGate
from nse_quant.features.feature_service import SpotFeatureSnapshot


def make_snapshot(
    trend_15m: float | None,
    trend_60m: float | None,
    rv: float | None = 0.10,
    vwap_distance: float | None = 0.001,
) -> SpotFeatureSnapshot:
    return SpotFeatureSnapshot(
        symbol="NIFTY",
        ts=pd.Timestamp.now(tz=UTC),
        close=25000.0,
        return_1m=0.0001,
        rv_1m_30=rv,
        atr_1m_14=5.0,
        vwap_distance_1m=vwap_distance,
        volume_zscore_1m_30=0.5,
        trend_15m=trend_15m,
        atr_15m_14=10.0,
        range_position_15m=0.5,
        trend_60m=trend_60m,
        atr_60m_14=20.0,
        range_position_60m=0.5,
    )


def test_gate_passes_when_features_align() -> None:
    gate = SpotFeatureGate()
    result = gate.evaluate(make_snapshot(0.001, 0.002))

    assert result.passed
    assert result.reasons == []


def test_gate_rejects_misaligned_trend() -> None:
    gate = SpotFeatureGate()
    result = gate.evaluate(make_snapshot(0.001, -0.002))

    assert not result.passed
    assert "multi_timeframe_trend_misaligned" in result.reasons


def test_gate_rejects_missing_snapshot() -> None:
    gate = SpotFeatureGate()
    result = gate.evaluate(None)

    assert not result.passed
    assert result.reasons == ["spot_features_unavailable"]

def test_gate_rejects_stale_snapshot() -> None:
    gate = SpotFeatureGate(max_age_seconds=60)

    snapshot = make_snapshot(0.001, 0.002)
    stale_snapshot = SpotFeatureSnapshot(
        **{
            **snapshot.__dict__,
            "ts": pd.Timestamp.now(tz=UTC) - pd.Timedelta(minutes=5),
        }
    )

    result = gate.evaluate(stale_snapshot)

    assert not result.passed
    assert "spot_features_stale" in result.reasons