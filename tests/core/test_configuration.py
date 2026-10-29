from pathlib import Path

import pytest
import yaml

from nse_quant.core.settings import Settings, get_settings


def test_yaml_load(tmp_path: Path):
    settings = get_settings()
    strategy_profile = settings.get_strategy_profile("iron_condor_monitor")
    assert settings.safety.dry_run is True
    assert settings.safety.trading_enabled is False
    strategy_profile = settings.get_strategy_profile("iron_condor_monitor")
    assert strategy_profile.enabled is True
    assert strategy_profile.strategy_type == "iron_condor"
    assert strategy_profile.wing_distance_points == 200
    assert strategy_profile.min_credit == 20
    assert strategy_profile.risk.max_open_positions == 1
    effective_risk = settings.get_effective_risk_settings("iron_condor_monitor")
    effective_exits = settings.get_effective_exit_settings("iron_condor_monitor")

    assert effective_risk.max_open_positions == 1
    assert effective_exits.iv_collapse_pct == 20


def test_live_mode_is_blocked():
    data = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))

    data["safety"].update(
        {
            "trading_enabled": True,
            "dry_run": False,
            "paper_trading": False,
        }
    )

    with pytest.raises(ValueError):
        Settings.model_validate(data)


def test_strategy_risk_spread_override():
    settings = Settings.model_validate(
        {
            "risk": {"max_spread_pct": 0.03},
            "strategies": {
                "iron_condor_monitor": {
                    "enabled": True,
                    "strategy_type": "iron_condor",
                    "underlyings": ["NIFTY"],
                    "wing_distance_points": 200,
                    "min_credit": 20,
                    "risk": {"max_spread_pct": 0.05},
                }
            },
        }
    )

    effective = settings.get_effective_risk_settings("iron_condor_monitor")

    assert effective.max_spread_pct == 0.05
