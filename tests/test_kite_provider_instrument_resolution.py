from datetime import UTC, datetime

import pytest

from nse_quant.core.settings import get_settings
from nse_quant.market_data.kite_provider import (
    InstrumentResolutionError,
    KiteMarketDataProvider,
)


class FakeKite:
    def __init__(
        self,
        instruments: list[dict],
        candles: list[dict] | None = None,
    ) -> None:
        self._instruments = instruments
        self._candles = candles or []
        self.calls: list[dict] = []

    def instruments(self, exchange: str) -> list[dict]:
        assert exchange == "NSE"
        return self._instruments

    def historical_data(self, **kwargs: object) -> list[dict]:
        self.calls.append(kwargs)
        return self._candles


@pytest.fixture
def settings():
    return get_settings()


def test_resolves_nifty_index_token(settings) -> None:
    kite = FakeKite(
        instruments=[
            {
                "exchange": "NSE",
                "segment": "INDICES",
                "instrument_type": "EQ",
                "tradingsymbol": "NIFTY 50",
                "instrument_token": 256265,
            }
        ],
    )
    provider = KiteMarketDataProvider(kite)

    assert provider.resolve_spot_instrument_token("NIFTY") == 256265


def test_resolves_stock_equity_token(settings) -> None:
    kite = FakeKite(
        instruments=[
            {
                "exchange": "NSE",
                "segment": "NSE",
                "instrument_type": "EQ",
                "tradingsymbol": "RELIANCE",
                "instrument_token": 738561,
            }
        ],
    )
    provider = KiteMarketDataProvider(kite)

    assert provider.resolve_spot_instrument_token("RELIANCE") == 738561


def test_rejects_ambiguous_equity(settings) -> None:
    kite = FakeKite(
        instruments=[
            {
                "exchange": "NSE",
                "segment": "NSE",
                "instrument_type": "EQ",
                "tradingsymbol": "RELIANCE",
                "instrument_token": 1,
            },
            {
                "exchange": "NSE",
                "segment": "NSE",
                "instrument_type": "EQ",
                "tradingsymbol": "RELIANCE",
                "instrument_token": 2,
            },
        ],
    )
    provider = KiteMarketDataProvider(kite)

    with pytest.raises(InstrumentResolutionError):
        provider.resolve_spot_instrument_token("RELIANCE")


def test_get_historical_candles_uses_index_token(settings) -> None:
    candle = {
        "date": datetime(2026, 10, 16, 9, 15, tzinfo=UTC),
        "open": 25000.0,
        "high": 25100.0,
        "low": 24950.0,
        "close": 25050.0,
        "volume": 0,
    }
    kite = FakeKite(
        instruments=[
            {
                "exchange": "NSE",
                "segment": "INDICES",
                "instrument_type": "EQ",
                "tradingsymbol": "NIFTY 50",
                "instrument_token": 256265,
            }
        ],
        candles=[candle],
    )
    provider = KiteMarketDataProvider(kite)

    candles = provider.get_historical_candles(
        symbol="NIFTY",
        interval="1m",
        from_dt=datetime(2026, 10, 16, 9, 15),
        to_dt=datetime(2026, 10, 16, 9, 16),
    )

    assert kite.calls[0]["instrument_token"] == 256265
    assert kite.calls[0]["interval"] == "minute"

    assert len(candles) == 1
    assert candles[0]["symbol"] == "NIFTY"
    assert candles[0]["interval"] == "1m"
    assert candles[0]["instrument_token"] == 256265
