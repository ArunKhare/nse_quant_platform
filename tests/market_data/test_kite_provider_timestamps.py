"""Verify REST timestamp mapping through both provider entry points."""

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import Mock

import pytest

from nse_quant.core.models import Instrument, OptionType
from nse_quant.market_data import chain
from nse_quant.market_data.kite_provider import (
    KiteMarketDataProvider,
)

EXPIRY = date(2026, 11, 5)


def make_provider(
    monkeypatch: pytest.MonkeyPatch,
    raw_quote: dict[str, Any],
) -> KiteMarketDataProvider:
    instrument = Instrument(
        tradingsymbol="NIFTY-TEST-CE",
        instrument_token=101,
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=24_000.0,
        option_type=OptionType.CE,
        lot_size=1,
    )

    kite = Mock()
    kite.quote.return_value = {
        "NFO:NIFTY-TEST-CE": raw_quote,
    }

    provider = KiteMarketDataProvider(kite, underlying="NIFTY")

    monkeypatch.setattr(
        provider,
        "_load_nfo_instruments",
        lambda: [
            {
                "name": "NIFTY",
                "instrument_type": "CE",
            }
        ],
    )
    monkeypatch.setattr(
        provider,
        "get_spot",
        lambda: 24_000.0,
    )
    monkeypatch.setattr(
        chain,
        "discover_chain",
        lambda *args, **kwargs: (EXPIRY, [instrument]),
    )
    monkeypatch.setattr(
        chain,
        "discover_chain_multi_expiry",
        lambda *args, **kwargs: [(EXPIRY, [instrument])],
    )

    return provider


@pytest.mark.parametrize("multi_expiry", [False, True])
def test_rest_timestamp_mapping(
    monkeypatch: pytest.MonkeyPatch,
    multi_expiry: bool,
) -> None:
    provider = make_provider(
        monkeypatch,
        {
            "last_price": 100.0,
            "timestamp": datetime(2026, 10, 30, 15, 40, 0),
            "last_trade_time": datetime(2026, 10, 30, 15, 39, 59),
            "oi": 100_000,
            "volume": 500,
            "depth": {
                "buy": [{"price": 99.0}],
                "sell": [{"price": 101.0}],
            },
        },
    )

    snapshot = provider.get_chain_snapshots()[0] if multi_expiry else provider.get_chain_snapshot()
    quote = snapshot.quotes[0]

    assert quote.exchange_ts == datetime(2026, 10, 30, 10, 10, 0, tzinfo=UTC)
    assert quote.trade_ts == datetime(2026, 10, 30, 10, 9, 59, tzinfo=UTC)
    assert quote.received_at == snapshot.ts
    assert snapshot.ts.utcoffset() is not None
    assert quote.bid == 99.0
    assert quote.ask == 101.0


@pytest.mark.parametrize("multi_expiry", [False, True])
def test_missing_exchange_time_is_not_fabricated(
    monkeypatch: pytest.MonkeyPatch,
    multi_expiry: bool,
) -> None:
    provider = make_provider(
        monkeypatch,
        {
            "last_price": 100.0,
            "last_trade_time": datetime(2026, 10, 30, 15, 39, 59),
            "depth": {
                "buy": [{"price": 0.0}],
                "sell": [{"price": 0.0}],
            },
        },
    )

    snapshot = provider.get_chain_snapshots()[0] if multi_expiry else provider.get_chain_snapshot()
    quote = snapshot.quotes[0]

    assert quote.exchange_ts is None
    assert quote.trade_ts is not None
    assert quote.bid == 0.0
    assert quote.ask == 0.0
    assert quote.received_at == snapshot.ts
