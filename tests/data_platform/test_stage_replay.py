"""Tests for complete exact replay of stages that actually run."""

from __future__ import annotations

from nse_quant.data_platform.stage_replay import (
    StageRecord,
    replay_stage,
    replay_stage_chain,
)


def _identity_evaluator(inputs: dict) -> dict:
    return dict(inputs)


def _record(stage: str, inputs: dict, outcome: dict) -> StageRecord:
    return StageRecord(stage=stage, inputs=inputs, outcome=outcome)


def test_single_stage_replay_matches():
    record = _record("strategy", dict(x=1), dict(x=1))
    result = replay_stage(record=record, evaluator=_identity_evaluator)
    assert result.replayed is True
    assert result.outcome_matches is True
    assert result.reason == "OUTCOME_MATCHES"


def test_single_stage_replay_mismatch():
    record = _record("strategy", dict(x=1), dict(x=2))
    result = replay_stage(record=record, evaluator=_identity_evaluator)
    assert result.replayed is True
    assert result.outcome_matches is False
    assert result.reason == "OUTCOME_MISMATCH"


def test_chain_replay_in_order():
    records = [
        _record("strategy", dict(x=1), dict(x=1)),
        _record("portfolio_risk", dict(y=2), dict(y=2)),
    ]
    evaluators = dict(
        strategy=_identity_evaluator,
        portfolio_risk=_identity_evaluator,
    )
    results = replay_stage_chain(records=records, evaluators=evaluators)
    assert len(results) == 2
    assert all(r.replayed for r in results)
    assert all(r.outcome_matches for r in results)


def test_chain_missing_evaluator_refused():
    records = [_record("execution", dict(z=3), dict(z=3))]
    evaluators = dict(strategy=_identity_evaluator)
    results = replay_stage_chain(records=records, evaluators=evaluators)
    assert len(results) == 1
    assert results[0].replayed is False
    assert results[0].reason == "NO_EVALUATOR_FOR_STAGE"


def test_evaluator_error_refused():
    def bad_evaluator(inputs: dict) -> dict:
        raise ValueError("boom")

    record = _record("strategy", dict(x=1), dict(x=1))
    result = replay_stage(record=record, evaluator=bad_evaluator)
    assert result.replayed is False
    assert result.outcome_matches is False
    assert result.reason == "EVALUATOR_ERROR:ValueError"


def test_non_callable_evaluator_refused():
    record = _record("strategy", dict(x=1), dict(x=1))
    result = replay_stage(record=record, evaluator="not_callable")
    assert result.replayed is False
    assert result.reason == "EVALUATOR_NOT_CALLABLE"
