import pytest

from nse_quant.core.settings import Settings


def test_candle_intervals_use_nested_configuration() -> None:
    settings = Settings()

    assert settings.market_data.candle_intervals["1m"].kite_interval == "minute"
    assert settings.market_data.candle_intervals["15m"].kite_interval == "15minute"
    assert settings.market_data.candle_intervals["60m"].kite_interval == "60minute"
    assert settings.market_data.candle_intervals["day"].kite_interval == "day"


def test_empty_candle_intervals_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Settings.model_validate(
            {
                "market_data": {
                    "candle_intervals": {},
                }
            }
        )