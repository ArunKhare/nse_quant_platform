"""Multi-horizon NIFTY strategy profiles; research registry only, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyProfile:
    profile_id: str
    horizon: str
    underlying: str
    entry_style: str
    exit_style: str
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
            "entry_style": self.entry_style,
            "exit_style": self.exit_style,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "allowed_regimes": list(self.allowed_regimes),
            "description": self.description,
            "decision_eligibility_asserted": self.decision_eligibility_asserted,
        }


PROFILES: tuple[StrategyProfile, ...] = (
    StrategyProfile(
        profile_id="nifty_intraday_iron_condor",
        horizon="intraday",
        underlying="NIFTY",
        entry_style="defined_risk_credit",
        exit_style="target_or_stop",
        risk_per_trade_pct=0.5,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Intraday NIFTY iron condor; defined-risk credit structure with "
        "target/stop exits.",
    ),
    StrategyProfile(
        profile_id="nifty_swing_iron_condor",
        horizon="swing",
        underlying="NIFTY",
        entry_style="defined_risk_credit",
        exit_style="target_or_stop",
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("RANGE", "LOW_VOL", "TREND"),
        description="Swing NIFTY iron condor; multi-day defined-risk credit structure.",
    ),
    StrategyProfile(
        profile_id="nifty_positional_butterfly",
        horizon="positional",
        underlying="NIFTY",
        entry_style="defined_risk_debit",
        exit_style="target_or_stop",
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Positional NIFTY butterfly; defined-risk debit structure for "
        "range-bound regimes.",
    ),
    StrategyProfile(
        profile_id="nifty_intraday_butterfly",
        horizon="intraday",
        underlying="NIFTY",
        entry_style="defined_risk_debit",
        exit_style="target_or_stop",
        risk_per_trade_pct=0.5,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL"),
        description="Intraday NIFTY butterfly; defined-risk debit structure for "
        "range-bound regimes.",
    ),
    StrategyProfile(
        profile_id="nifty_swing_butterfly",
        horizon="swing",
        underlying="NIFTY",
        entry_style="defined_risk_debit",
        exit_style="target_or_stop",
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("RANGE", "LOW_VOL", "TREND"),
        description="Swing NIFTY butterfly; multi-day defined-risk debit structure.",
    ),
    StrategyProfile(
        profile_id="nifty_positional_iron_condor",
        horizon="positional",
        underlying="NIFTY",
        entry_style="defined_risk_credit",
        exit_style="target_or_stop",
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("RANGE", "LOW_VOL", "TREND"),
        description="Positional NIFTY iron condor; multi-day defined-risk credit structure.",
    ),
)

_BY_ID = {profile.profile_id: profile for profile in PROFILES}
_BY_HORIZON: dict[str, list[StrategyProfile]] = {}
for _profile in PROFILES:
    _BY_HORIZON.setdefault(_profile.horizon, []).append(_profile)


def get_profile(profile_id: str) -> StrategyProfile | None:
    return _BY_ID.get(profile_id)


def list_profiles(
    *, horizon: str | None = None, underlying: str | None = None
) -> list[StrategyProfile]:
    result = list(PROFILES)
    if horizon is not None:
        result = [p for p in result if p.horizon == horizon]
    if underlying is not None:
        result = [p for p in result if p.underlying == underlying]
    return result


def list_horizons() -> list[str]:
    return sorted(_BY_HORIZON)


def profile_summary(profile: StrategyProfile) -> dict[str, Any]:
    return profile.to_dict()


def all_profiles_summary() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PROFILES]
