"""Tests for full stage-chain replay."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.full_stage_chain_replay import (
    FULL_STAGE_CHAIN,
    FullStageRecord,
    replay_full_stage_chain,
)


def _identity(inputs: dict) -> dict:
    return dict(inputs)


def _records():
    return [
        FullStageRecord(stage=stage, inputs=dict(x=i), outcome=dict(x=i))
        for i, stage in enumerate(FULL_STAGE_CHAIN)
    ]


def _evaluators():
    return {stage: _identity for stage in FULL_STAGE_CHAIN}


def test_full_chain_replays_in_order():
    results = replay_full_stage_chain(records=_records(), evaluators=_evaluators())
    assert len(results) == 7
    assert all(r.replayed for r in results)
    assert all(r.outcome_matches for r in results)
    assert [r.stage for r in results] == list(FULL_STAGE_CHAIN)


def test_chain_order_mismatch_refused():
    records = _records()
    records[0], records[1] = records[1], records[0]
    with pytest.raises(ValueError, match="ORDER_MISMATCH"):
        replay_full_stage_chain(records=records, evaluators=_evaluators())


def test_missing_evaluator_refused():
    evaluators = _evaluators()
    del evaluators["strategy"]
    results = replay_full_stage_chain(records=_records(), evaluators=evaluators)
    assert len(results) == 7
    strategy_result = next(r for r in results if r.stage == "strategy")
    assert strategy_result.replayed is False
    assert strategy_result.reason == "NO_EVALUATOR_FOR_STAGE"


def test_evaluator_error_refused():
    def bad_evaluator(inputs: dict) -> dict:
        raise ValueError("boom")

    evaluators = _evaluators()
    evaluators["strategy"] = bad_evaluator
    results = replay_full_stage_chain(records=_records(), evaluators=evaluators)
    assert len(results) == 7
    strategy_result = next(r for r in results if r.stage == "strategy")
    assert strategy_result.replayed is False
    assert strategy_result.reason == "EVALUATOR_ERROR:ValueError"


def test_non_list_records_refused():
    with pytest.raises(ValueError, match="RECORDS_LIST_REQUIRED"):
        replay_full_stage_chain(records="not_a_list", evaluators=_evaluators())


def test_non_dict_evaluators_refused():
    with pytest.raises(ValueError, match="EVALUATORS_DICT_REQUIRED"):
        replay_full_stage_chain(records=_records(), evaluators="not_a_dict")
