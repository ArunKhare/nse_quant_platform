from typing import Any

from nse_quant.ui.dash_app import market_features_table, market_metric_cards


def _component_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(_component_text(item) for item in value)
    children = getattr(value, "children", None)
    return _component_text(children) if children is not None else ""


def test_market_features_table_separates_regime_vocabularies() -> None:
    snapshot = {
        "features": {
            "spot": 25000.0,
            "intraday_shape": "TREND_UP",
            "regime": "BULL|NORMAL",
        },
        "strategy_eligibility": {
            "details": {
                "regime_label": "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP",
                "institutional_regime_evidence": {
                    "available": True,
                    "complete": True,
                    "regime_label_canonical": True,
                    "regime_label_eligible": False,
                    "thresholds_provisional": True,
                    "missing_components": ["term_structure"],
                },
                "market_context": {"daily_trend_vol": "BULL|NORMAL"},
            }
        },
    }

    rendered = _component_text(market_features_table(snapshot))

    assert "Institutional regime (eligibility evidence)" in rendered
    assert "Daily market context (legacy)" in rendered
    assert "Intraday shape" in rendered
    assert "HIGH IV CONTANGO NORMAL SKEW HIGH VOL CHOP" in rendered
    assert "BULL|NORMAL" in rendered
    assert "Classifier evidence readiness" in rendered
    assert "thresholds_provisional=True" in rendered
    assert "term_structure" in rendered
    assert "Regime" not in rendered


def test_market_metric_cards_display_intraday_shape_not_legacy_regime() -> None:
    snapshot = {
        "features": {
            "intraday_shape": "TREND_UP",
            "regime": "BULL|NORMAL",
        }
    }

    rendered = _component_text(market_metric_cards(snapshot))

    assert "Intraday shape" in rendered
    assert "TREND UP" in rendered
    assert "BULL|NORMAL" not in rendered
