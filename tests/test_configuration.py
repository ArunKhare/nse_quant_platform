from pathlib import Path

import pytest
import yaml

from nse_quant.core.settings import Settings, get_settings


def test_yaml_load():
    settings = get_settings()

    assert settings.safety.dry_run is True
    assert settings.safety.trading_enabled is False
    strategy_profile  =  settings.get_strategy_profile(
        "iron_condor_monitor"
    )
    assert strategy_profile.enabled is True
    assert strategy_profile.strategy_type == "iron_condor"
    assert strategy_profile.wing_distance_points == 200
    assert strategy_profile.min_credit == 20
    assert strategy_profile.risk.max_open_positions == 1
    effective_risk = settings.get_effective_risk_settings(
        "iron_condor_monitor"
    )

    assert effective_risk.max_open_positions == 1

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