"""Regime-aware strategy eligibility evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore


@dataclass(frozen=True)
class RegimePolicy:
    strategy: str
    allowed_regimes: set[str]
    blocked_regimes: set[str] = field(default_factory=set)
    require_iv_rank_available: bool = True

    @classmethod
    def from_dict(
        cls,
        strategy: str,
        payload: dict[str, Any],
    ) -> RegimePolicy:
        return cls(
            strategy=strategy,
            allowed_regimes=set(
                payload.get("allowed_regimes", [])
            ),
            blocked_regimes=set(
                payload.get("blocked_regimes", [])
            ),
            require_iv_rank_available=bool(
                payload.get(
                    "require_iv_rank_available",
                    True,
                )
            ),
        )


@dataclass
class PolicyDecision:
    strategy: str
    regime: str | None
    allowed: bool
    reasons: list[str]
    checks: dict[str, bool]


def load_policy(
    path: str,
    *,
    strategy: str = "iron_condor",
) -> RegimePolicy:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    strategy_payload = payload.get(strategy)

    if not isinstance(strategy_payload, dict):
        raise TypeError(
            f"No policy configured for strategy: {strategy}"
        )

    return RegimePolicy.from_dict(
        strategy=strategy,
        payload=strategy_payload,
    )


def evaluate_regime_policy(
    *,
    store: DuckDBStore,
    policy: RegimePolicy,
    underlying: str,
    iv_rank: float | None,
) -> PolicyDecision:
    regime_record = store.latest_daily_iv_regime(
        underlying=underlying
    )

    regime = (
        regime_record["iv_regime"]
        if regime_record
        else None
    )

    reasons: list[str] = []
    checks: dict[str, bool] = {}

    regime_available = regime is not None
    checks["regime_available"] = regime_available

    if not regime_available:
        reasons.append("IV regime unavailable")
    else:
        checks["regime_not_blocked"] = (
            regime not in policy.blocked_regimes
        )

        if regime in policy.blocked_regimes:
            reasons.append(
                f"Regime blocked: {regime}"
            )

        if policy.allowed_regimes:
            checks["regime_allowed"] = (
                regime in policy.allowed_regimes
            )

            if regime not in policy.allowed_regimes:
                reasons.append(
                    f"Regime not allowed: {regime}"
                )
        else:
            checks["regime_allowed"] = True

    iv_rank_available = iv_rank is not None
    checks["iv_rank_available"] = iv_rank_available

    if (
        policy.require_iv_rank_available
        and not iv_rank_available
    ):
        reasons.append("IV rank unavailable")

    allowed = all(
        (
            checks.get("regime_available", False),
            checks.get("regime_not_blocked", False),
            checks.get("regime_allowed", False),
        )
    )

    if policy.require_iv_rank_available:
        allowed = allowed and iv_rank_available

    return PolicyDecision(
        strategy=policy.strategy,
        regime=regime,
        allowed=allowed,
        reasons=reasons,
        checks=checks,
    )