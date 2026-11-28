"""Regression tests for per-cycle option quote and spot refresh."""

from datetime import UTC, date, datetime

from nse_quant.core.models import ChainSnapshot, Instrument, OptionQuote, OptionType
from nse_quant.market_data import kite_stream


def _snapshot() -> ChainSnapshot:
    instrument = Instrument(
        tradingsymbol="NIFTY26NOV25000CE",
        instrument_token=101,
        underlying="NIFTY",
        expiry=date(2026, 11, 26),
        strike=25_000.0,
        option_type=OptionType.CE,
        lot_size=75,
    )
    quote = OptionQuote(
        instrument=instrument,
        instrument_token=101,
        ltp=100.0,
        bid=99.0,
        ask=101.0,
        volume=10,
        oi=20,
        iv=0.18,
        delta=0.5,
        gamma=0.01,
        vega=2.0,
        theta=-1.0,
    )
    return ChainSnapshot(
        underlying="NIFTY",
        spot=25_000.0,
        expiry=date(2026, 11, 26),
        quotes=[quote],
    )


def test_refresh_snapshot_quotes_uses_current_option_and_spot_ticks(monkeypatch) -> None:
    snapshot = _snapshot()
    observed = {}

    def capture_enrichment(*, quote, spot, expiry, now, rate):
        observed["mid"] = quote.mid
        observed["spot"] = spot
        observed["expiry"] = expiry
        observed["now"] = now
        observed["rate"] = rate
        quote.iv = 0.24
        quote.delta = 0.61
        quote.gamma = 0.02
        quote.vega = 3.0
        quote.theta = -1.5
        return quote

    monkeypatch.setattr(kite_stream, "enrich_quote", capture_enrichment)
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    kite_stream._refresh_snapshot_quotes(
        snapshot,
        {
            999: {"ltp": 25_125.0},
            101: {
                "ltp": 120.0,
                "bid": 119.0,
                "ask": 121.0,
                "volume": 30,
                "oi": 40,
            },
        },
        spot_token=999,
        now=now,
        rate=0.07,
    )

    quote = snapshot.quotes[0]
    assert snapshot.spot == 25_125.0
    assert (quote.ltp, quote.bid, quote.ask, quote.volume, quote.oi) == (
        120.0, 119.0, 121.0, 30, 40
    )
    assert observed == {
        "mid": 120.0,
        "spot": 25_125.0,
        "expiry": date(2026, 11, 26),
        "now": now,
        "rate": 0.07,
    }
    assert (quote.iv, quote.delta, quote.gamma, quote.vega, quote.theta) == (
        0.24, 0.61, 0.02, 3.0, -1.5
    )


def test_refresh_snapshot_quotes_clears_stale_greeks_before_recalculation(monkeypatch) -> None:
    snapshot = _snapshot()
    observed = {}

    def no_valid_iv(*, quote, spot, expiry, now, rate):
        observed["analytics_before_recalculation"] = (
            quote.iv, quote.delta, quote.gamma, quote.vega, quote.theta
        )
        return quote

    monkeypatch.setattr(kite_stream, "enrich_quote", no_valid_iv)
    kite_stream._refresh_snapshot_quotes(
        snapshot,
        {},
        spot_token=999,
        now=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        rate=0.07,
    )

    assert observed["analytics_before_recalculation"] == (None, None, None, None, None)
