"""Actual refusal kernel/service tests; no native source computations substituted."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import native_refusal_decision as kernel
from nse_quant.data_platform.native_refusal_service import evaluate_native_refusal

T = datetime(2026, 1, 1, tzinfo=UTC)


def request(**changes):
    value = kernel.RefusalRequest("synthetic-attempt", "a" * 64, "b" * 64, T, T, "c" * 40)
    return replace(value, **changes)


@pytest.mark.parametrize(
    "changes,stage,reason",
    [
        ({}, "kill_switch", "KILL_SWITCH_STATE_UNKNOWN"),
        ({"kill_switch": "ACTIVE", "live_requested": True}, "kill_switch", "KILL_SWITCH_ACTIVE"),
        (
            {"kill_switch": "INACTIVE", "live_requested": True},
            "safety_boundary",
            "LIVE_EXECUTION_DISABLED",
        ),
        ({"kill_switch": "INACTIVE", "dry_run": False}, "safety_boundary", "DRY_RUN_REQUIRED"),
        (
            {"kill_switch": "INACTIVE", "paper_only": False},
            "safety_boundary",
            "PAPER_ONLY_BOUNDARY_REQUIRED",
        ),
        ({"kill_switch": "INACTIVE"}, "publication_admission", "ADMISSION_NOT_OBSERVED"),
    ],
    ids=["unknown", "kill-precedence", "live", "dry-run", "paper", "missing-admission"],
)
def test_exact_order_and_no_later_stage_execution(changes, stage, reason):
    raw = evaluate_native_refusal(None, request=request(**changes))
    entry = kernel.replay_refusal_entry(raw, expected_decision_id=kernel.sha(raw))
    result = entry["result"]
    assert result["failed_stage"] == stage
    assert result["reason_codes"] == [reason]
    assert result["status"] == "REFUSED_PRE_STRATEGY"
    blocked = False
    for item in result["stage_trace"]:
        if item["stage"] == stage:
            assert item["status"] == "BLOCKED"
            blocked = True
        elif blocked:
            assert item["status"] == "NOT_RUN"
        else:
            assert item["status"] == "PASSED"
    assert result["strategy_evaluated"] is False
    assert result["portfolio_risk_evaluated"] is False
    assert result["execution_attempted"] is False
    assert result["order_emitted"] is False
    assert result["complete_strategy_replay_asserted"] is False
    assert {x["state"] for x in result["input_inventory"]} == {"NOT_OBSERVED"}


def test_early_safety_never_probes_supplied_source_or_imports_strategy(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("nse_quant.strategy", "nse_quant.risk", "nse_quant.execution")):
            raise AssertionError("Early refusal imported execution-adjacent code")
        if (
            name == "nse_quant.data_platform"
            and len(args) > 2
            and {"publication_admission", "quote_publication_reader"}.intersection(
                args[2] or (),
            )
        ):
            raise AssertionError("Early refusal imported native source evaluation")
        if name in {
            "nse_quant.data_platform.publication_admission",
            "nse_quant.data_platform.quote_publication_reader",
        }:
            raise AssertionError("Early refusal imported native source evaluation")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    raw = evaluate_native_refusal(object(), request=request())
    assert (
        kernel.replay_refusal_entry(raw, expected_decision_id=kernel.sha(raw))["result"][
            "admission_observed"
        ]
        is False
    )


@pytest.mark.parametrize(
    "field",
    ["strategy_evaluated", "execution_attempted", "order_emitted", "decision_eligibility_asserted"],
    ids=["strategy", "execution", "order", "eligibility"],
)
def test_rehashed_complete_result_tampering_is_rejected(field):
    raw = evaluate_native_refusal(None, request=request())
    value = json.loads(raw)
    value["result"][field] = True
    changed = kernel.canonical(value)
    with pytest.raises(kernel.NativeDecisionRejected, match="COMPLETE_REPLAY_MISMATCH"):
        kernel.replay_refusal_entry(changed, expected_decision_id=kernel.sha(changed))


def test_context_drift_is_not_fingerprint_refresh():
    raw = evaluate_native_refusal(None, request=request())
    value = json.loads(raw)
    value["frozen_input"]["runtime"]["python_version"] = "0.0"
    changed = kernel.canonical(value)
    with pytest.raises(kernel.NativeDecisionRejected, match="CODE_OR_RUNTIME_CONTEXT_DRIFT"):
        kernel.replay_refusal_entry(changed, expected_decision_id=kernel.sha(changed))


def test_strict_bytes_wrong_pin_and_actual_payload_bound():
    raw = evaluate_native_refusal(None, request=request())
    for changed, expected in ((raw, "0" * 64), (raw + b" ", kernel.sha(raw + b" "))):
        with pytest.raises(kernel.NativeDecisionRejected):
            kernel.replay_refusal_entry(changed, expected_decision_id=expected)
    with pytest.raises(kernel.NativeDecisionRejected, match="BYTE_BOUND"):
        kernel.replay_refusal_entry(b"x" * (kernel.MAX_BYTES + 1), expected_decision_id="0" * 64)


def test_full_reviewed_revision_and_strict_safety_types():
    for changes in (
        dict(reviewed_code_revision="78272d0"),
        dict(live_requested=1),
        dict(kill_switch="AUTO"),
        dict(knowledge_cutoff=T.replace(tzinfo=None)),
    ):
        with pytest.raises(kernel.NativeDecisionRejected):
            request(**changes)
