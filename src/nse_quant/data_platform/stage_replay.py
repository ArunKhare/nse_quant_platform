"""Complete exact replay of stages that actually run.

Re-derives the same outcome from the same inputs for stages that actually ran
(strategy, portfolio_risk), extending the existing refusal decision's pre-strategy
replay to cover the full stage chain. Addresses the "complete exact replay of
stages that actually run" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class StageRecord(BaseModel):
    stage: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outcome: dict[str, Any] = Field(default_factory=dict)


class ReplayResult(BaseModel):
    stage: str
    replayed: bool
    outcome_matches: bool
    reason: str


def replay_stage(
    *,
    record: StageRecord,
    evaluator: Callable[[dict[str, Any]], dict[str, Any]],
) -> ReplayResult:
    """Replay a single stage and compare the re-derived outcome to the recorded one."""
    if type(record) is not StageRecord:
        return ReplayResult(
            stage="unknown",
            replayed=False,
            outcome_matches=False,
            reason="INVALID_RECORD",
        )
    if not callable(evaluator):
        return ReplayResult(
            stage=record.stage,
            replayed=False,
            outcome_matches=False,
            reason="EVALUATOR_NOT_CALLABLE",
        )

    try:
        re_derived = evaluator(record.inputs)
    except Exception as exc:
        return ReplayResult(
            stage=record.stage,
            replayed=False,
            outcome_matches=False,
            reason=f"EVALUATOR_ERROR:{type(exc).__name__}",
        )

    matches = re_derived == record.outcome
    return ReplayResult(
        stage=record.stage,
        replayed=True,
        outcome_matches=matches,
        reason="OUTCOME_MATCHES" if matches else "OUTCOME_MISMATCH",
    )


def replay_stage_chain(
    *,
    records: list[StageRecord],
    evaluators: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
) -> list[ReplayResult]:
    """Replay a chain of stages that actually ran, in order."""
    if type(records) is not list:
        raise ValueError("RECORDS_LIST_REQUIRED")
    if type(evaluators) is not dict:
        raise ValueError("EVALUATORS_DICT_REQUIRED")

    results: list[ReplayResult] = []
    for record in records:
        evaluator = evaluators.get(record.stage)
        if evaluator is None:
            results.append(
                ReplayResult(
                    stage=record.stage,
                    replayed=False,
                    outcome_matches=False,
                    reason="NO_EVALUATOR_FOR_STAGE",
                )
            )
            continue
        results.append(replay_stage(record=record, evaluator=evaluator))
    return results
