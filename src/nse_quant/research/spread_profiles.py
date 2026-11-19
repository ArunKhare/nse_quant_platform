"""NIFTY directional defined-risk spread profiles; research registry only,
no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpreadProfile:
    profile_id: str
    horizon: str
    underlying: str
    direction: str
    structure: str
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
            "direction": self.direction,
            "structure": self.structure,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "allowed_regimes": list(self.allowed_regimes),
            "description": self.description,
            "decision_eligibility_asserted": self.decision_eligibility_asserted,
        }


PROFILES: tuple[SpreadProfile, ...] = (
    SpreadProfile(
        profile_id="nifty_intraday_bull_call_spread",
        horizon="intraday",
        underlying="NIFTY",
        direction="BULLISH",
        structure="bull_call_spread",
        risk_per_trade_pct=0.5,
        max_concurrent_positions=2,
        allowed_regimes=("TREND", "HIGH_VOL"),
        description="Intraday NIFTY bull call spread; defined-risk debit structure "
        "for bullish regimes.",
    ),
    SpreadProfile(
        profile_id="nifty_swing_bull_call_spread",
        horizon="swing",
        underlying="NIFTY",
        direction="BULLISH",
        structure="bull_call_spread",
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("TREND", "HIGH_VOL", "RANGE"),
        description="Swing NIFTY bull call spread; multi-day defined-risk debit structure.",
    ),
    SpreadProfile(
        profile_id="nifty_positional_bull_call_spread",
        horizon="positional",
        underlying="NIFTY",
        direction="BULLISH",
        structure="bull_call_spread",
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("TREND", "HIGH_VOL", "RANGE"),
        description="Positional NIFTY bull call spread; multi-week defined-risk debit structure.",
    ),
    SpreadProfile(
        profile_id="nifty_intraday_bear_put_spread",
        horizon="intraday",
        underlying="NIFTY",
        direction="BEARISH",
        structure="bear_put_spread",
        risk_per_trade_pct=0.5,
        max_concurrent_positions=2,
        allowed_regimes=("TREND", "HIGH_VOL"),
        description="Intraday NIFTY bear put spread; defined-risk debit structure"
        " for bearish regimes.",
    ),
    SpreadProfile(
        profile_id="nifty_swing_bear_put_spread",
        horizon="swing",
        underlying="NIFTY",
        direction="BEARISH",
        structure="bear_put_spread",
        risk_per_trade_pct=0.75,
        max_concurrent_positions=3,
        allowed_regimes=("TREND", "HIGH_VOL", "RANGE"),
        description="Swing NIFTY bear put spread; multi-day defined-risk debit structure.",
    ),
    SpreadProfile(
        profile_id="nifty_positional_bear_put_spread",
        horizon="positional",
        underlying="NIFTY",
        direction="BEARISH",
        structure="bear_put_spread",
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        allowed_regimes=("TREND", "HIGH_VOL", "RANGE"),
        description="Positional NIFTY bear put spread; multi-week defined-risk debit structure.",
    ),
)

_BY_ID = {profile.profile_id: profile for profile in PROFILES}
_BY_DIRECTION: dict[str, list[SpreadProfile]] = {}
_BY_HORIZON: dict[str, list[SpreadProfile]] = {}
for _profile in PROFILES:
    _BY_DIRECTION.setdefault(_profile.direction, []).append(_profile)
    _BY_HORIZON.setdefault(_profile.horizon, []).append(_profile)


def get_profile(profile_id: str) -> SpreadProfile | None:
    return _BY_ID.get(profile_id)


def list_profiles(
    *, horizon: str | None = None, direction: str | None = None, underlying: str | None = None
) -> list[SpreadProfile]:
    result = list(PROFILES)
    if horizon is not None:
        result = [p for p in result if p.horizon == horizon]
    if direction is not None:
        result = [p for p in result if p.direction == direction]
    if underlying is not None:
        result = [p for p in result if p.underlying == underlying]
    return result


def list_horizons() -> list[str]:
    return sorted(_BY_HORIZON)


def list_directions() -> list[str]:
    return sorted(_BY_DIRECTION)


def profile_summary(profile: SpreadProfile) -> dict[str, Any]:
    return profile.to_dict()


def all_profiles_summary() -> list[dict[str, Any]]:
    return [p.to_dict() for p in PROFILES]
