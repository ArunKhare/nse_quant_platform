"""Point-in-time feature availability contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FeatureAvailability(StrEnum):
    READY = "READY"
    WARMING_UP = "WARMING_UP"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class FeatureRequirement:
    feature: str
    required_observations: int
    interval: str | None = None
    source: str = "spot_candles"


CORE_1M_REQUIREMENTS = (
    FeatureRequirement("return_1m", 1, "1m"),
    FeatureRequirement("rv_1m_30", 30, "1m"),
    FeatureRequirement("atr_1m_14", 14, "1m"),
    FeatureRequirement("vwap_distance_1m", 1, "1m"),
    FeatureRequirement("volume_zscore_1m_30", 30, "1m"),
)

HTF_REQUIREMENTS = (
    FeatureRequirement("trend_15m", 50, "15m"),
    FeatureRequirement("atr_15m_14", 14, "15m"),
    FeatureRequirement("trend_60m", 50, "60m"),
    FeatureRequirement("atr_60m_14", 14, "60m"),
)

IV_REQUIREMENTS = (
    FeatureRequirement("iv_rank", 252, None, "option_stream"),
    FeatureRequirement("iv_rv_spread", 30, None, "aligned_daily"),
)


@dataclass(frozen=True)
class FeatureAvailabilityReport:
    symbol: str
    as_of: Any
    core_status: FeatureAvailability
    htf_status: FeatureAvailability
    iv_status: FeatureAvailability
    overall_status: FeatureAvailability
    observations: dict[str, int]
    missing: list[str]
    reasons: list[str]

    @property
    def can_evaluate_new_entries(self) -> bool:
        return self.overall_status == FeatureAvailability.READY

    @property
    def can_monitor_open_positions(self) -> bool:
        return self.core_status == FeatureAvailability.READY
