from pathlib import Path
import pytest,yaml
from core.settings import Settings,load_settings

def test_yaml_load():
    s=load_settings(Path("config/settings.yaml"))
    assert s.safety.dry_run is True and s.safety.trading_enabled is False
    assert s.strategy.iron_condor_monitor.wing_distance_points==200
    assert s.risk.max_daily_loss==25000

def test_live_blocked():
    data=yaml.safe_load(Path("config/settings.yaml").read_text())
    data["safety"].update(trading_enabled=True,dry_run=False,paper_trading=False)
    with pytest.raises(ValueError): Settings.model_validate(data)
