from pathlib import Path

import pytest
import yaml

from nse_quant.core.settings import Settings, get_settings


def test_yaml_load():
    settings = get_settings(Path("config/settings.yaml"))
    data = settings.model_dump()

    assert data["safety"]["dry_run"] is True and data["safety"]["trading_enabled"] is False
    assert data["strategy"]["iron_condor_monitor"]["wing_distance_points"] == 200
    assert data["risk"]["max_daily_loss"] == 25000


def test_live_blocked():
    data = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    data["safety"].update(trading_enabled=True, dry_run=False, paper_trading=False)

    with pytest.raises(ValueError):
        Settings.model_validate(data)
