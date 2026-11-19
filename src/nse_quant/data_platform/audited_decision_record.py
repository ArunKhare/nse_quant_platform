"""Actual audited native strategy/risk decision record.

Produces an audited decision record with a fingerprint for a strategy or
portfolio-risk decision, without granting eligibility or enabling live trading.
Addresses the "actual audited native strategy/risk decisions" sub-gap of gate 6
from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    stage: str  # "strategy" or "portfolio_risk"
    inputs: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)
    decision_eligibility_asserted: bool = False


class AuditedDecision(BaseModel):
    stage: str
    fingerprint: str
    recorded: bool
    reason: str
    decision_eligibility_asserted: bool = False


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def audit_decision(
    *,
    record: DecisionRecord,
) -> AuditedDecision:
    """Audit a strategy or portfolio-risk decision into a fingerprinted record."""
    if type(record) is not DecisionRecord:
        return AuditedDecision(
            stage="unknown",
            fingerprint="",
            recorded=False,
            reason="INVALID_RECORD",
        )
    if record.stage not in ("strategy", "portfolio_risk"):
        return AuditedDecision(
            stage=record.stage,
            fingerprint="",
            recorded=False,
            reason="UNSUPPORTED_STAGE",
        )

    fingerprint = _sha(
        _canonical(
            [
                record.stage,
                record.inputs,
                record.outcome,
            ]
        )
    )
    return AuditedDecision(
        stage=record.stage,
        fingerprint=fingerprint,
        recorded=True,
        reason="DECISION_AUDITED",
        decision_eligibility_asserted=False,
    )
