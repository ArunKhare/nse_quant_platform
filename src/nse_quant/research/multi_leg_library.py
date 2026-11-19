"""Multi-leg NIFTY strategy library; research registry only, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MultiLegProfile:
    profile_id: str
    horizon: str
    underlying: str
    structure: str
    legs: tuple[str, ...]
    risk_per_trade_pct: float
    max_concurrent_positions: int
    allowed_regimes: tuple[str, ...]
    description: str
    decision_eligibility_asserted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "horizon": self.horizon,
            "underlying": self.underlying,
            "structure": self.structure,
            "legs": list(self.legs),
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "allowed_regimes": list(self.allowed_regimes),
            "description": self.description,
            "decision_eligibility_asserted": self.decision_eligibility_asserted,
        }


PROFILES: tuple[MultiLegProfile, ...] = (
    MultiLegProfile(
        profile_id="nifty_intraday_iron_fly",
        horizon="intraday",
        underlying="NIFTY",
        structure="iron_fly",
        legs=("short_call_atm", "short_put_atm", "long_call_wing", "long_put_wing"),
        risk_per_trade_pct=0.5,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Intraday NIFTY iron fly; 4-leg defined-risk structure for range-bound regimes.",
    ),
    MultiLegProfile(
        profile_id="nifty_swing_iron_fly",
        horizon="swing",
        underlying="NIFTY",
        structure="iron_fly",
        legs=("short_call_atm", "short_put_atm", "long_call_wing", "long_put_wing"),
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("RANGE", "LOW_VOL", "TREND"),
        description="Swing NIFTY iron fly; multi-day 4-leg defined-risk structure.",
    ),
    MultiLegProfile(
        profile_id="nifty_positional_iron_fly",
        horizon="positional",
        underlying="NIFTY",
        structure="iron_fly",
        legs=("short_call_atm", "short_put_atm", "long_call_wing", "long_put_wing"),
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Positional NIFTY iron fly; multi-week 4-leg defined-risk structure.",
    ),
    MultiLegProfile(
        profile_id="nifty_swing_calendar_spread",
        horizon="swing",
        underlying="NIFTY",
        structure="calendar_spread",
        legs=("long_near_expiry", "short_far_expiry"),
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("RANGE", "LOW_VOL", "TREND"),
        description="Swing NIFTY calendar spread; 2-leg volatility term-structure strategy.",
    ),
    MultiLegProfile(
        profile_id="nifty_positional_calendar_spread",
        horizon="positional",
        underlying="NIFTY",
        structure="calendar_spread",
        legs=("long_near_expiry", "short_far_expiry"),
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Positional NIFTY calendar spread; multi-week 2-leg volatility term-structure strategy.",
    ),
    MultiLegProfile(
        profile_id="nifty_swing_ratio_spread",
        horizon="swing",
        underlying="NIFTY",
        structure="ratio_spread",
        legs=("long_atm", "short_otm_1", "short_otm_2"),
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("TREND", "HIGH_VOL", "RANGE"),
        description="Swing NIFTY ratio spread; 3-leg directional structure with defined risk.",
    ),
)

_BY_ID = {profile.profile_id: profile for profile in PROFILES}
_BY_STRUCTURE: dict[str, list[MultiLegProfile]] = {}
_BY_HORIZON: dict[str, list[MultiLegProfile]] = {}
for _profile in PROFILES:
    _BY_STRUCTURE.setdefault(_profile.structure, []).append(_profile)
    _BY_HORIZON.setdefault(_profile.horizon, []).append(_profile)


def get_profile(profile_id: str) -> MultiLegProfile | None:
    return _BY_ID.get(profile_id)


def list_profiles(
    *, horizon: str | None = None, structure: str | None = None, underlying: str | None = None
) -> list[MultiLegProfile]:
    result = list(PROFILES)
    if horizon is not None:
        result = [p for p in result if p.horizon == horizon]
    if structure is not None:
        result = [p for p in result if p.structure == structure]
    if underlying is not None:
        result = [p for p in result if p.underlying == underlying]
    return result


def list_horizons() -> list[str]:
    return sorted(_BY_HORIZON)


def list_structures() -> list[str]:
    return sorted(_BY_STRUCTURE)


def profile_summary(profile: MultiLegProfile) -> dict[str, Any]:
    return profile.to_dict()


def all_profiles_summary() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PROFILES]
