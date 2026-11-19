"""Integration tests for institutional regime label assembly."""

from __future__ import annotations

from datetime import UTC, date, datetime

from nse_quant.core.models import ChainSnapshot, Instrument, MarketFeatures, OptionQuote, OptionType
from nse_quant.research.evidence_plugins.institutional_regime import InstitutionalRegimePlugin


def _instrument(option_type: OptionType) -> Instrument:
    return Instrument(
        tradingsymbol="SYNTHETIC",
        instrument_token=258,
        underlying="NIFTY",
        expiry=date(2026, 12, 31),
        strike=100.0,
        option_type=option_type,
        lot_size=1,
    )


def _snapshot(put_iv: float | None, call_iv: float | None) -> ChainSnapshot:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    quotes = [
        OptionQuote(instrument_token=258, instrument=_instrument(OptionType.PE), iv=put_iv),
        OptionQuote(instrument_token=259, instrument=_instrument(OptionType.CE), iv=call_iv),
    ]
    return ChainSnapshot(
        ts=at, underlying="NIFTY", spot=100.0, expiry=date(2026, 12, 31), quotes=quotes
    )


def _features() -> MarketFeatures:
    return MarketFeatures(
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        underlying="NIFTY",
        spot=100.0,
        expiry=date(2026, 12, 31),
        atm_iv=0.2,
    )


class _Conn:
    @staticmethod
    def execute(*args, **kwargs):
        class _Result:
            @staticmethod
            def fetchall():
                return []

            @staticmethod
            def fetchone():
                return None

        return _Result()


class _Store:
    conn = _Conn


def _plugin() -> InstitutionalRegimePlugin:
    from nse_quant.core.settings import InstitutionalRegimeSettings

    return InstitutionalRegimePlugin(store=_Store(), settings=InstitutionalRegimeSettings())


def _context(snapshot, features):
    return type(
        "Context",
        (),
        {
            "ts": datetime(2026, 1, 1, tzinfo=UTC),
            "symbol": "NIFTY",
            "snapshot": snapshot,
            "features": features,
            "spot_instrument_token": 257,
        },
    )()


def test_regime_label_none_when_incomplete():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=0.25, call_iv=0.20)
    result = plugin.build(_context(snapshot, _features()))
    assert result["regime_label"] is None
    assert result["complete"] is False
    assert result["missing_components"]


def test_all_four_components_present():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=0.21, call_iv=0.20)
    result = plugin.build(_context(snapshot, _features()))
    assert set(result["components"]) == {"iv_state", "skew", "price_action", "term_structure"}
    assert "not_implemented" not in str(result["components"])
    assert result["classifier_version"] == "institutional_iv_term_components_v4"
