"""Full stage-chain replay.

Replays the full 7-stage chain (kill_switch, safety_boundary, publication_admission,
native_inputs, strategy, portfolio_risk, execution) in order, verifying the full
chain, without granting eligibility or enabling live trading. Addresses the
"full stage-chain replay" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

FULL_STAGE_CHAIN = (
    "kill_switch",
    "safety_boundary",
    "publication_admission",
    "native_inputs",
    "strategy",
    "portfolio_risk",
    "execution",
)


class FullStageRecord(BaseModel):
    stage: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)


class FullChainReplayResult(BaseModel):
    stage: str
    replayed: bool
    outcome_matches: bool
    reason: str


def replay_full_stage_chain(
    *,
    records: list[FullStageRecord],
    evaluators: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
) -> list[FullChainReplayResult]:
    """Replay the full 7-stage chain in order, verifying the full chain."""
    if type(records) is not list:
        raise ValueError("RECORDS_LIST_REQUIRED")
    if type(evaluators) is not dict:
        raise ValueError("EVALUATORS_DICT_REQUIRED")

    # Verify the chain covers all 7 stages in order
    recorded_stages = [r.stage for r in records]
    if recorded_stages != list(FULL_STAGE_CHAIN):
        raise ValueError("STAGE_CHAIN_ORDER_MISMATCH")

    results: list[FullChainReplayResult] = []
    for record in records:
        evaluator = evaluators.get(record.stage)
        if evaluator is None:
            results.append(
                FullChainReplayResult(
                    stage=record.stage,
                    replayed=False,
                    outcome_matches=False,
                    reason="NO_EVALUATOR_FOR_STAGE",
                )
            )
            continue
        try:
            re_derived = evaluator(record.inputs)
        except Exception as exc:
            results.append(
                FullChainReplayResult(
                    stage=record.stage,
                    replayed=False,
                    outcome_matches=False,
                    reason=f"EVALUATOR_ERROR:{type(exc).__name__}",
                )
            )
            continue
        matches = re_derived == record.outcome
        results.append(
            FullChainReplayResult(
                stage=record.stage,
                replayed=True,
                outcome_matches=matches,
                reason="OUTCOME_MATCHES" if matches else "OUTCOME_MISMATCH",
            )
        )
    return results
