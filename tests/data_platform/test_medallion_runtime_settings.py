from pathlib import Path

import pytest

from nse_quant.core.settings import (
    load_settings,
)
from nse_quant.data_platform.runtime_settings import (
    execution_mode,
    expansion_underlyings,
    governance_retention_days,
    layer_root_path,
    live_execution_enabled,
    medallion_enabled,
    medallion_root_path,
)

# def test_live_medallion_requires_explicit_enablement():
#     with pytest.raises(ValueError):
#         MedallionSettings(
#             execution=MedallionExecutionSettings(
#                 mode="live",
#                 live_enabled=False,
#             ),
#             admission=MedallionAdmissionSettings(),
#         )


def test_medallion_settings_load_from_yaml():
    settings = load_settings()

    assert settings.medallion.enabled is True
    assert settings.medallion.root_path == Path("data/medallion")
    assert settings.medallion.bronze.root_path == Path("data/medallion/bronze")
    assert settings.medallion.silver.root_path == Path("data/medallion/silver")
    assert settings.medallion.gold.root_path == Path("data/medallion/gold")


def test_runtime_accessors_use_medallion_settings():
    assert medallion_enabled() is True
    assert medallion_root_path() == Path("data/medallion")
    assert layer_root_path("bronze") == Path("data/medallion/bronze")
    assert layer_root_path("silver") == Path("data/medallion/silver")
    assert layer_root_path("gold") == Path("data/medallion/gold")
    assert governance_retention_days() == 365
    assert execution_mode() == "paper"
    assert live_execution_enabled() is False
    assert expansion_underlyings() == ["NIFTY", "BANKNIFTY"]


def test_invalid_live_medallion_execution_is_rejected():

    with pytest.raises(ValueError):
        load_settings(Path("config/settings.yaml")).model_copy(update={})
