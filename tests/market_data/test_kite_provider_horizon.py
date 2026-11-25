"""Provider integration with real discovery and mocked Kite requests."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nse_quant.analytics.constant_maturity_inputs import SurfaceInputError
from nse_quant.core.constants import IST
from nse_quant.market_data import kite_provider as module
from nse_quant.market_data.expiry_selection import ExpirySelectionError
from nse_quant.market_data.surface_input_adapter import surface_from_batch

AS_OF = date(2026, 1, 2)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        # Jan 1 in UTC, Jan 2 in IST: provider must select by IST calendar day.
        instant = datetime(2026, 1, 1, 20, tzinfo=UTC)
        return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)


def make_provider(monkeypatch: pytest.MonkeyPatch, days: tuple[int, ...]):
    monkeypatch.setattr(module, "datetime", Clock)
    settings = SimpleNamespace(
        universe=SimpleNamespace(underlying="NIFTY", strikes_per_side=2),
        analytics=SimpleNamespace(expiries_per_snapshot=2, capture_horizon_days=90),
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    rows = []
    for index, day in enumerate(days):
        for offset, kind in enumerate(("CE", "PE")):
            expiry = AS_OF + timedelta(days=day)
            rows.append(
                dict(
                    name="NIFTY",
                    instrument_type=kind,
                    expiry=expiry.isoformat(),
                    strike=25000,
                    instrument_token=index * 2 + offset + 1,
                    tradingsymbol=f"NIFTY-{day}-{kind}",
                    lot_size=75,
                )
            )
    # A different underlying must not supply horizon coverage or quotes.
    rows.append(
        dict(
            name="BANKNIFTY",
            instrument_type="CE",
            expiry=(AS_OF + timedelta(days=200)).isoformat(),
            strike=50000,
            instrument_token=9999,
            tradingsymbol="BANK-200-CE",
            lot_size=30,
        )
    )
    kite = Mock()
    kite.instruments.return_value = rows
    kite.quote.side_effect = lambda keys: {
        key: {
            "last_price": 100.0,
            "timestamp": "2026-01-02T01:00:00+05:30",
            "last_trade_time": "2026-01-02T01:00:00+05:30",
            "oi": 100_000,
            "volume": 1000,
            "depth": {"buy": [{"price": 99}], "sell": [{"price": 101}]},
        }
        for key in keys
    }
    provider = module.KiteMarketDataProvider(kite)
    monkeypatch.setattr(provider, "get_spot", lambda: 25000.0)
    return provider, kite


def test_provider_captures_full_horizon_not_legacy_two_expiries(monkeypatch) -> None:
    provider, kite = make_provider(monkeypatch, (-1, 0, 7, 30, 60, 90, 91, 120))
    snapshots = provider.get_chain_snapshots()
    assert [(item.expiry - AS_OF).days for item in snapshots] == [0, 7, 30, 60, 90, 91]
    assert kite.quote.call_count == 6
    assert len({item.acquisition_id for item in snapshots}) == 1
    assert len({item.run_id for item in snapshots}) == len(snapshots)
    for item in snapshots:
        assert len(item.quotes) == 2
        assert all(q.instrument.expiry == item.expiry for q in item.quotes)
        assert all(q.instrument.underlying == "NIFTY" for q in item.quotes)
        assert all(q.received_at == item.ts for q in item.quotes)
    requested = [key for call in kite.quote.call_args_list for key in call.args[0]]
    assert len(requested) == 12
    assert not any("120" in key or "BANK" in key or "NIFTY--1-" in key for key in requested)


@pytest.mark.parametrize("days", [(7, 30), (7, 30, 90)])
def test_missing_beyond_horizon_never_falls_back(monkeypatch, days) -> None:
    provider, kite = make_provider(monkeypatch, days)
    with pytest.raises(ExpirySelectionError, match="beyond_horizon"):
        provider.get_chain_snapshots()
    kite.quote.assert_not_called()


def test_explicit_wider_horizon_is_supported(monkeypatch) -> None:
    provider, _ = make_provider(monkeypatch, (7, 30, 91, 120, 121, 150))
    snapshots = provider.get_chain_snapshots(horizon_days=120)
    assert [(item.expiry - AS_OF).days for item in snapshots] == [7, 30, 91, 120, 121]


@pytest.mark.parametrize("horizon", [0, 89, True, 90.5, "90"])
def test_invalid_or_reduced_horizon_rejected_before_acquisition(monkeypatch, horizon) -> None:
    provider, kite = make_provider(monkeypatch, (30, 91))
    with pytest.raises(ValueError, match=">= 90"):
        provider.get_chain_snapshots(horizon_days=horizon)
    kite.instruments.assert_not_called()
    kite.quote.assert_not_called()


def test_missing_quote_does_not_acquire_later_expiry_as_substitute(monkeypatch) -> None:
    provider, kite = make_provider(monkeypatch, (30, 60, 91, 120))
    kite.quote.side_effect = lambda keys: {}
    snapshots = provider.get_chain_snapshots()
    assert [(item.expiry - AS_OF).days for item in snapshots] == [30, 60, 91]
    assert all(q.ltp is None and q.bid is None and q.ask is None for item in snapshots for q in item.quotes)


def test_multi_expiry_provider_batch_reaches_forward_validation(monkeypatch) -> None:
    provider, _ = make_provider(monkeypatch, (20, 40, 80, 100))
    snapshots = provider.get_chain_snapshots()
    expiry_closes = {
        item.expiry: datetime.combine(item.expiry, time(15, 30), tzinfo=IST)
        for item in snapshots
    }
    with pytest.raises(SurfaceInputError, match="matching_expiry_forward_missing"):
        surface_from_batch(
            snapshots,
            [],
            expiry_closes=expiry_closes,
            calendar_reference_id="calendar-fixture-v1",
            as_of=Clock.now(UTC),
        )
