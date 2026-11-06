"""Institutional regime skew component.

Computes point-in-time put/call IV skew from a chain snapshot for the
institutional regime plugin. This is observational evidence only; it does not
authorize execution or create a decision gate.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InstitutionalRegimeSkewSettings(BaseModel):
    skew_threshold: float = Field(default=0.03, ge=0.0)


def compute_skew(
    *,
    put_iv: float | None,
    call_iv: float | None,
    settings: InstitutionalRegimeSkewSettings,
) -> dict[str, Any]:
    if put_iv is None or call_iv is None:
        return {
            "available": False,
            "complete": False,
            "state": None,
            "skew": None,
            "reason": "missing_iv_inputs",
            "decision_eligibility_asserted": False,
        }

    if put_iv <= 0 or call_iv <= 0:
        return {
            "available": False,
            "complete": False,
            "state": None,
            "skew": None,
            "reason": "invalid_iv_inputs",
            "decision_eligibility_asserted": False,
        }

    skew = put_iv - call_iv
    if skew > settings.skew_threshold:
        state = "HIGH_PUT_SKEW"
    elif skew < -settings.skew_threshold:
        state = "HIGH_CALL_SKEW"
    else:
        state = "NORMAL_SKEW"

    return {
        "available": True,
        "complete": True,
        "state": state,
        "skew": skew,
        "threshold": settings.skew_threshold,
        "decision_eligibility_asserted": False,
    }
