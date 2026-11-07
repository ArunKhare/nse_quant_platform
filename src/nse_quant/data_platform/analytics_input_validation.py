"""Native analytics input validation.

Validates a dict of analytics inputs (feature inputs, thresholds) against a
defined schema, without granting eligibility or enabling live trading. Addresses
the "native analytics inputs beyond the 9 requirements" sub-gap of gate 6 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyticsInputSchema(BaseModel):
    feature_names: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)
    history_window: int = Field(default=0, ge=0)
    cold_start_policy: str = Field(default="reject")


class AnalyticsValidation(BaseModel):
    valid: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


def validate_analytics_inputs(
    *,
    inputs: dict[str, Any],
    schema: AnalyticsInputSchema,
) -> AnalyticsValidation:
    """Validate analytics inputs against the defined schema."""
    if type(inputs) is not dict:
        return AnalyticsValidation(valid=False, reasons=["INVALID_INPUTS"])

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []

    # Feature names must be non-empty strings
    features = inputs.get("feature_names", [])
    if not isinstance(features, list) or not all(isinstance(f, str) and f for f in features):
        checks.append(dict(check="feature_names", passed=False))
        reasons.append("INVALID_FEATURE_NAMES")
    else:
        checks.append(dict(check="feature_names", passed=True))

    # Thresholds must be numeric and non-negative
    thresholds = inputs.get("thresholds", {})
    if not isinstance(thresholds, dict) or not all(
        isinstance(v, (int, float)) and v >= 0 for v in thresholds.values()
    ):
        checks.append(dict(check="thresholds", passed=False))
        reasons.append("INVALID_THRESHOLDS")
    else:
        checks.append(dict(check="thresholds", passed=True))

    # History window must be non-negative int
    history = inputs.get("history_window", 0)
    if not isinstance(history, int) or history < 0:
        checks.append(dict(check="history_window", passed=False))
        reasons.append("INVALID_HISTORY_WINDOW")
    else:
        checks.append(dict(check="history_window", passed=True))

    # Cold-start policy must be one of the allowed values
    cold_start = inputs.get("cold_start_policy", "reject")
    if cold_start not in ("reject", "warn", "allow"):
        checks.append(dict(check="cold_start_policy", passed=False))
        reasons.append("INVALID_COLD_START_POLICY")
    else:
        checks.append(dict(check="cold_start_policy", passed=True))

    return AnalyticsValidation(
        valid=not reasons,
        reasons=reasons,
        checks=checks,
    )
