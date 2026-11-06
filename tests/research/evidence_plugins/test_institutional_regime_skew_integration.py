"""Integration tests for institutional regime skew component wiring."""

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
        OptionQuote(
            instrument_token=258,
            instrument=_instrument(OptionType.PE),
            iv=put_iv,
        ),
        OptionQuote(
            instrument_token=259,
            instrument=_instrument(OptionType.CE),
            iv=call_iv,
        ),
    ]
    return ChainSnapshot(
        ts=at,
        underlying="NIFTY",
        spot=100.0,
        expiry=date(2026, 12, 31),
        quotes=quotes,
    )


def _features() -> MarketFeatures:
    return MarketFeatures(
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        underlying="NIFTY",
        spot=100.0,
        expiry=date(2026, 12, 31),
        atm_iv=0.2,
    )


class _Store:
    class conn:
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


def _plugin() -> InstitutionalRegimePlugin:
    from nse_quant.core.settings import InstitutionalRegimeSettings

    return InstitutionalRegimePlugin(store=_Store(), settings=InstitutionalRegimeSettings())


def test_skew_component_wired_high_put_skew():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=0.25, call_iv=0.20)
    context = type(
        "Context",
        (),
        {
            "ts": datetime(2026, 1, 1, tzinfo=UTC),
            "symbol": "NIFTY",
            "snapshot": snapshot,
            "features": _features(),
        },
    )()
    result = plugin.build(context)
    skew = result["components"]["skew"]
    assert skew["available"] is True
    assert skew["complete"] is True
    assert skew["state"] == "HIGH_PUT_SKEW"
    assert "skew" not in result["missing_components"]


def test_skew_component_wired_normal():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=0.21, call_iv=0.20)
    context = type(
        "Context",
        (),
        {
            "ts": datetime(2026, 1, 1, tzinfo=UTC),
            "symbol": "NIFTY",
            "snapshot": snapshot,
            "features": _features(),
        },
    )()
    result = plugin.build(context)
    skew = result["components"]["skew"]
    assert skew["available"] is True
    assert skew["complete"] is True
    assert skew["state"] == "NORMAL_SKEW"


def test_skew_component_missing_iv():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=None, call_iv=0.20)
    context = type(
        "Context",
        (),
        {
            "ts": datetime(2026, 1, 1, tzinfo=UTC),
            "symbol": "NIFTY",
            "snapshot": snapshot,
            "features": _features(),
        },
    )()
    result = plugin.build(context)
    skew = result["components"]["skew"]
    assert skew["available"] is False
    assert skew["reason"] == "missing_iv_inputs"
    assert "skew" in result["missing_components"]


def test_price_action_still_pending():
    plugin = _plugin()
    snapshot = _snapshot(put_iv=0.21, call_iv=0.20)
    context = type(
        "Context",
        (),
        {
            "ts": datetime(2026, 1, 1, tzinfo=UTC),
            "symbol": "NIFTY",
            "snapshot": snapshot,
            "features": _features(),
        },
    )()
    result = plugin.build(context)
    assert result["components"]["price_action"]["reason"] == "not_implemented"
    assert "price_action" in result["missing_components"]
