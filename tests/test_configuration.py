from pathlib import Path

import pytest
import yaml

from nse_quant.core.settings import Settings, get_settings


def test_yaml_load():
    settings = get_settings()

    assert settings.safety.dry_run is True
    assert settings.safety.trading_enabled is False
    strategy = settings.strategy
    iron_condor_monitor = strategy.iron_condor_monitor
    assert iron_condor_monitor.wing_distance_points == 200
    assert settings.risk.max_daily_loss == 25000


def test_live_mode_is_blocked():
    data = yaml.safe_load(
        Path("config/settings.yaml").read_text(encoding="utf-8")
    )

    data["safety"].update(
        {
            "trading_enabled": True,
            "dry_run": False,
            "paper_trading": False,
        }
    )

    with pytest.raises(ValueError):
        Settings.model_validate(data)