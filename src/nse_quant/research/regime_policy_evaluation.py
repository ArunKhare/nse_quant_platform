"""Evaluate a configured strategy regime policy against historical outcomes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from nse_quant.core.settings import (
    IronCondorProfileSettings,
    Settings,
)
from nse_quant.research.regime_policy import select_regime_policy
from nse_quant.research.trade_outcomes import (
    TradeOutcome,
    load_trade_outcomes,
)


@dataclass(frozen=True)
class RegimePolicyEvaluation:
    symbol: str
    strategy_id: str
    as_of: str
    start_date: str
    end_date: str
    profile_enabled: bool
    configured_allowed_regimes: list[str]
    configured_blocked_regimes: list[str]
    learned_policy_status: str
    learned_allowed_regimes: list[str]
    effective_allowed_regimes: list[str]
    regime_coverage: dict[str, int]
    total_outcomes: int
    actionable: bool
    reason: str


def evaluate_regime_policy(
    settings: Settings,
    *,
    symbol: str,
    strategy_id: str,
    start_date: str,
    end_date: str,
    min_trades_per_regime: int = 10,
) -> tuple[RegimePolicyEvaluation, list[TradeOutcome]]:
    profile = settings.get_strategy_profile(strategy_id)

    if not isinstance(profile, IronCondorProfileSettings):
        raise TypeError(
            f"{strategy_id!r} must use IronCondorProfileSettings"
        )

    outcomes = load_trade_outcomes(
        settings.storage.db_path,
        symbol=symbol,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
    )

    learned = select_regime_policy(
        outcomes,
        min_trades=min_trades_per_regime,
    )

    configured_allowed = list(profile.regime_policy.allowed_regimes)
    configured_blocked = set(profile.regime_policy.blocked_regimes)

    if learned.is_usable:
        effective_allowed = sorted(
            set(learned.allowed_regimes) - configured_blocked
        )
        learned_status = learned.selection_status
        reason = "learned_policy_ready"
    else:
        effective_allowed = sorted(
            set(configured_allowed) - configured_blocked
        )
        learned_status = learned.selection_status
        reason = (
            "configured_policy_fallback"
            if effective_allowed
            else "no_allowed_regimes"
        )

    coverage: dict[str, int] = {}
    for outcome in outcomes:
        coverage[outcome.regime] = coverage.get(outcome.regime, 0) + 1

    actionable = (
        profile.enabled
        and bool(effective_allowed)
        and reason != "no_allowed_regimes"
    )

    evaluation = RegimePolicyEvaluation(
        symbol=symbol,
        strategy_id=strategy_id,
        as_of=datetime.now(UTC).isoformat(),
        start_date=start_date,
        end_date=end_date,
        profile_enabled=profile.enabled,
        configured_allowed_regimes=configured_allowed,
        configured_blocked_regimes=sorted(configured_blocked),
        learned_policy_status=learned_status,
        learned_allowed_regimes=sorted(learned.allowed_regimes),
        effective_allowed_regimes=effective_allowed,
        regime_coverage=coverage,
        total_outcomes=len(outcomes),
        actionable=actionable,
        reason=reason,
    )

    return evaluation, outcomes


def export_evaluation(
    evaluation: RegimePolicyEvaluation,
    output_path: Path,
    *,
    expires_in_days: int = 7,
) -> None:
    payload = asdict(evaluation)
    payload["expires_at"] = (
        datetime.now(UTC) + timedelta(days=expires_in_days)
    ).isoformat()
    payload["risk_limits"] = {}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

def resolve_effective_regimes(
    profile: IronCondorProfileSettings,
    *,
    learned_policy: dict[str, Any] | None,
) -> tuple[list[str], str, str | None]:
    policy_status = (
        learned_policy.get("selection_status")
        if learned_policy
        else None
    )

    learned_allowed = set(
        learned_policy.get("allowed_regimes") or []
    ) if learned_policy else set()

    configured_allowed = set(profile.regime_policy.allowed_regimes)
    blocked = set(profile.regime_policy.blocked_regimes)

    if policy_status == "READY":
        effective = sorted(learned_allowed - blocked)
        source = "learned_policy"
    else:
        effective = sorted(configured_allowed - blocked)
        source = "configured_profile"

    return effective, source, policy_status