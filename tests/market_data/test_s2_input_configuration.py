"""Small installed-settings/provider integration checks for the S2 wiring."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from nse_quant.core.settings import AnalyticsSettings, MarketDataSettings
from nse_quant.market_data import kite_provider as module


def test_typed_acquisition_horizon_does_not_change_minimum_completeness():
    settings = AnalyticsSettings(capture_horizon_days=120, expiries_per_snapshot=2)
    assert settings.capture_horizon_days == 120 and settings.expiries_per_snapshot == 2
    assert MarketDataSettings().india_vix.enabled is False


@pytest.mark.parametrize("value", [89, True, 90.5, "90"])
def test_typed_horizon_rejects_reduced_or_coerced_values(value):
    with pytest.raises(ValidationError):
        AnalyticsSettings(capture_horizon_days=value)


def test_provider_reads_configured_horizon_instead_of_a_hardcoded_default(monkeypatch):
    settings = SimpleNamespace(
        analytics=SimpleNamespace(capture_horizon_days=120),
        universe=SimpleNamespace(
            underlying="NIFTY",
            strikes_per_side=2,
        ),
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    provider = module.KiteMarketDataProvider(
        kite=SimpleNamespace(),
        underlying="NIFTY",
    )

    monkeypatch.setattr(provider, "_load_nfo_instruments", lambda: [])
    monkeypatch.setattr(provider, "get_spot", lambda: 100.0)

    captured = []

    def discover(**kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(
        module.chain,
        "discover_chain_for_horizon",
        discover,
    )

    assert provider.get_chain_snapshots() == []
    assert captured[0]["horizon_days"] == 120


def test_both_settings_files_keep_acquisition_and_completeness_distinct():
    root = Path(__file__).resolve().parents[2]
    for filename in ("settings.yaml", "settings.test.yaml"):
        data = yaml.safe_load((root / "config" / filename).read_text(encoding="utf-8"))
        assert data["analytics"]["capture_horizon_days"] >= 90
        assert data["analytics"]["expiries_per_snapshot"] == 2
        assert data["market_data"]["india_vix"]["enabled"] is False
