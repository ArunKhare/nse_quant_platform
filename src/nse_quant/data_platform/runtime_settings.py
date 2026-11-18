"""Safe runtime access to centralized Medallion settings."""

from __future__ import annotations

from pathlib import Path

from nse_quant.core.settings import get_settings


def medallion_enabled() -> bool:
    return get_settings().medallion.enabled


def medallion_root_path() -> Path:
    return get_settings().medallion.root_path


def layer_root_path(layer: str) -> Path:
    settings = get_settings().medallion

    if layer == "bronze":
        return settings.bronze.root_path
    if layer == "silver":
        return settings.silver.root_path
    if layer == "gold":
        return settings.gold.root_path

    raise ValueError(f"Unsupported Medallion layer: {layer!r}")


def governance_retention_days() -> int:
    return get_settings().medallion.governance.retention_days


def execution_mode() -> str:
    return get_settings().medallion.execution.mode.value


def live_execution_enabled() -> bool:
    return get_settings().medallion.execution.live_enabled


def expansion_underlyings() -> list[str]:
    return list(get_settings().medallion.expansion.underlyings)
