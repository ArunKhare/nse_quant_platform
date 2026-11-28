"""Canonical decision-to-risk boundary; no execution or policy authority."""

from __future__ import annotations

import math
from typing import Any

from nse_quant.core.regime_registry import is_canonical_regime_label

VERSION = "canonical_decision_risk_context_v1"


def canonical_regime_for_risk(evidence: dict[str, Any]) -> str | None:
    """Never use daily/spot context or provisional classification as a risk key."""
    payload = evidence.get("institutional_regime")
    if not isinstance(payload, dict):
        return None
    if payload.get("available") is not True or payload.get("complete") is not True:
        return None
    if payload.get("thresholds_provisional") is not False:
        return None
    if payload.get("decision_eligibility_asserted") is not False:
        return None
    label = payload.get("regime_label")
    return label if isinstance(label, str) and is_canonical_regime_label(label) else None


def canonical_risk_rejection(regime: str, policy: dict[str, Any] | None) -> str | None:
    """Check readiness before the loop's configured-limit shortcut is evaluated.

    None means continue through the existing limit builder, not authorize a
    trade. No policy, label translation, static fallback or evidence is created.
    """
    if not is_canonical_regime_label(regime):
        return "non_canonical_regime"
    if not isinstance(policy, dict) or policy.get("selection_status") != "READY":
        return "policy_not_ready"
    allowed = policy.get("allowed_regimes")
    if not isinstance(allowed, (list, tuple, set, frozenset)):
        return "invalid_canonical_policy"
    if any(not is_canonical_regime_label(label) for label in allowed):
        return "non_canonical_policy"
    for field in ("risk_limits", "regime_metrics"):
        entries = policy.get(field, {})
        if not isinstance(entries, dict):
            return "invalid_canonical_policy"
        if any(not is_canonical_regime_label(label) for label in entries):
            return "non_canonical_policy"
        if any(not isinstance(value, dict) for value in entries.values()):
            return "invalid_canonical_policy"
    if "risk_limits" not in policy:
        return "invalid_canonical_policy"
    if regime not in allowed:
        return "regime_not_allowed"
    configured = policy["risk_limits"].get(regime)
    if configured:
        if type(configured.get("allowed")) is not bool:
            return "invalid_configured_risk_limits"
        for field in (
            "max_lots_per_order",
            "max_open_positions",
            "max_notional_exposure",
            "max_portfolio_vega",
            "max_daily_loss",
        ):
            value = configured.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                return "invalid_configured_risk_limits"
            if field in {"max_lots_per_order", "max_open_positions"} and int(value) != value:
                return "invalid_configured_risk_limits"
    return None
