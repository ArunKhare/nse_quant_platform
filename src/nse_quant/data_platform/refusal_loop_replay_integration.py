"""Refusal-to-full-loop-replay integration.

Integrates the refusal kernel's audited record (from refusal_audited_record.py)
into the full decision loop replay (full_decision_loop_replay.py), without
granting eligibility or enabling live trading. Addresses the "integrate the
audited record back into the full stage-chain replay" sub-gap of gate 6 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_record import AuditedDecision
from nse_quant.data_platform.refusal_audited_record import (
    build_audited_record_from_refusal,
)


def integrate_refusal_into_loop(
    *,
    refusal_result: dict[str, Any],
    existing_audited: AuditedDecision | None = None,
) -> dict[str, Any]:
    """Integrate the refusal kernel's audited record into the full loop replay."""
    if type(refusal_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_RESULT_OBJECT_REQUIRED",
            audited=None,
            existing_audited=None,
        )

    refusal_audited = build_audited_record_from_refusal(refusal_result=refusal_result)

    integrated = refusal_audited.recorded and (
        existing_audited is None or existing_audited.recorded
    )

    return dict(
        integrated=integrated,
        reason="REFUSAL_INTEGRATED_INTO_LOOP" if integrated else "REFUSAL_NOT_INTEGRATED",
        audited=refusal_audited,
        existing_audited=existing_audited,
    )
