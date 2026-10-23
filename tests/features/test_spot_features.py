import pandas as pd
import pytest

from nse_quant.features.spot_features import SpotFeatureBuilder


class FakeStore:
    def __init__(
        self,
        minute: pd.DataFrame,
        minute_15: pd.DataFrame,
        minute_60: pd.DataFrame,
    ) -> None:
        self._frames = {
            "1m": minute,
            "15m": minute_15,
            "60m": minute_60,
        }

    def read_spot_candles(
        self,
        symbol: str,
        interval: str,
        from_ts=None,
        to_ts=None,
    ) -> pd.DataFrame:
        return self._frames[interval].copy()


def make_candles(ts_values: list[str], close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": "NIFTY" * len(ts_values),
            "interval": ["1m"] * len(ts_values),
            "ts": pd.to_datetime(ts_values, utc=True),
            "open": [close] * len(ts_values),
            "high": [close + 1] * len(ts_values),
            "low": [close - 1] * len(ts_values),
            "close": [close] * len(ts_values),
            "volume": [100] * len(ts_values),
            "oi": [None] * len(ts_values),
        }
    )


def test_higher_timeframe_feature_available_only_after_close() -> None:
    minute = make_candles(
        [
            "2026-10-16 09:15:00",
            "2026-10-16 09:16:00",
            "2026-10-16 09:31:00",
        ],
        25000.0,
    )
    minute["symbol"] = "NIFTY"

    minute_15 = make_candles(
        [
            "2026-10-16 09:00:00",
            "2026-10-16 09:15:00",
        ],
        25000.0,
    )
    minute_15["symbol"] = "NIFTY"
    minute_15["interval"] = "15m"

    # Give the second 15m candle a different close so trend is non-null.
    minute_15.loc[1, "close"] = 25100.0
    minute_15.loc[1, "high"] = 25101.0
    minute_15.loc[1, "low"] = 25099.0

    store = FakeStore(minute, minute_15, pd.DataFrame())
    builder = SpotFeatureBuilder(store=store)

    features = builder.build("NIFTY")

    assert len(features) == 3

    # The 09:15 15m candle closes at 09:30.
    assert pd.isna(features.iloc[0]["trend_15m"])
    assert pd.isna(features.iloc[1]["trend_15m"])

    # The 09:15 15m bar becomes available at 09:30.
    assert pd.notna(features.iloc[2]["trend_15m"])
    assert features.iloc[2]["trend_15m"] == pytest.approx(25100.0 / 25000.0 - 1)
