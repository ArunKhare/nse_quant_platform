"""Pure refusal contracts and early real native safety reuse; no source attestation."""

import builtins
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform import native_window_refusal as kernel
from nse_quant.data_platform.native_window_refusal_service import evaluate_window_refusal


def request(**changes):
    args = dict(
        attempt_id="synthetic",
        publication_id="a" * 64,
        expected_publication_evidence_fingerprint="b" * 64,
        knowledge_cutoff=datetime(2026, 1, 1, tzinfo=UTC),
        economic_at=datetime(2026, 1, 1, tzinfo=UTC),
        reviewed_code_revision="a" * 40,
    )
    args.update(changes)
    return kernel.RefusalRequest(**args)


class ForbiddenSource:
    def __getattribute__(self, _name):
        raise AssertionError("early refusal must not probe source")


@pytest.mark.parametrize(
    "changes,stage,reason",
    [
        ({}, "kill_switch", "KILL_SWITCH_STATE_UNKNOWN"),
        ({"kill_switch": "ACTIVE"}, "kill_switch", "KILL_SWITCH_ACTIVE"),
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
    ],
    ids=["unknown", "active", "live", "not-dry-run", "not-paper-only"],
)
def test_actual_safety_order_before_source_probe(changes, stage, reason):
    raw = evaluate_window_refusal(ForbiddenSource(), request=request(**changes))
    value = kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))
    result = value["result"]
    assert result["status"] == "REFUSED_PRE_STRATEGY"
    assert result["failed_stage"] == stage
    assert result["reason_codes"] == [reason]
    assert not result["admission_observed"]
    assert all(i["state"] == "NOT_OBSERVED" for i in result["input_inventory"])
    stopped = kernel.requirements.STAGES.index(stage)
    assert [r["status"] for r in result["stage_trace"]] == (
        ["PASSED"] * stopped + ["BLOCKED"] + ["NOT_RUN"] * (6 - stopped)
    )
    assert not result["strategy_evaluated"]
    assert not result["order_emitted"]


def test_missing_source_is_not_fabricated_admission():
    raw = evaluate_window_refusal(None, request=request(kill_switch="INACTIVE"))
    result = kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))["result"]
    assert result["failed_stage"] == "publication_admission"
    assert result["reason_codes"] == ["WINDOW_ADMISSION_NOT_OBSERVED"]
    assert not result["admission_observed"]


def test_early_gate_does_not_import_window_admission_services(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        fromlist = kwargs.get("fromlist", args[2] if len(args) > 2 else ())
        if "legacy_window" in name or any("legacy_window" in str(x) for x in (fromlist or ())):
            raise AssertionError("window service import before safety")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as local:
        local.setattr(builtins, "__import__", guarded)
        raw = evaluate_window_refusal(ForbiddenSource(), request=request())
    assert kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))


def test_early_codec_rejects_supplied_receipts_before_dependency_import(monkeypatch):
    def forbidden():
        raise AssertionError("dependencies must not be observed")

    monkeypatch.setattr(kernel, "_dependencies", forbidden)
    with pytest.raises(ValueError, match="EARLY_GATE"):
        kernel.make_window_refusal_entry(request(), admission_receipts=(b"{}", b"{}"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "APPROVED"),
        ("strategy_evaluated", True),
        ("order_emitted", True),
        ("decision_eligibility_asserted", True),
        ("complete_strategy_replay_asserted", True),
    ],
    ids=["status", "strategy", "order", "eligibility", "full-strategy-replay"],
)
def test_rehashed_result_promotion_is_rejected(field, value):
    doc = json.loads(evaluate_window_refusal(None, request=request()))
    doc["result"][field] = value
    raw = kernel.canonical(doc)
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))


def test_later_stage_trace_cannot_be_relabelled_as_run():
    doc = json.loads(evaluate_window_refusal(None, request=request()))
    doc["result"]["stage_trace"][-1]["status"] = "PASSED"
    raw = kernel.canonical(doc)
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))


def test_runtime_and_dependency_context_cannot_be_rehashed_away():
    doc = json.loads(evaluate_window_refusal(None, request=request()))
    doc["frozen_input"]["runtime"]["profile"] = "invented"
    raw = kernel.canonical(doc)
    with pytest.raises(ValueError, match="RUNTIME_DRIFT"):
        kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))


@pytest.mark.parametrize(
    "receipts", [(b"{}",), (b"x" * 32769, b"{}")], ids=["partial-pair", "receipt-overflow"]
)
def test_receipt_component_bounds(receipts):
    with pytest.raises(ValueError, match="BOUNDED_ADMISSION"):
        kernel.make_window_refusal_entry(
            request(kill_switch="INACTIVE"), admission_receipts=receipts
        )


def test_entry_bound_before_json_parse():
    raw = b"x" * (kernel.MAX_BYTES + 1)
    with pytest.raises(ValueError, match="ENTRY_BYTE_BOUND"):
        kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))


def test_original_request_reuse_rejects_naive_axes_and_bool_safety():
    with pytest.raises(ValueError):
        request(knowledge_cutoff=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        replace(request(), dry_run=1)
