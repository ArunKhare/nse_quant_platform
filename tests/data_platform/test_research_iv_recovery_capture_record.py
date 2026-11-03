"""Pure codec tests; synthetic records do not establish native truth or audit proof."""

import json
from copy import deepcopy
from typing import Any

import pytest

from nse_quant.data_platform import research_iv_recovery_capture_record as record


def body():
    value: dict[str, Any] = dict.fromkeys(record.DENIALS, False)
    value.update(dict.fromkeys(record.NULLS))
    value.update(
        version=record.SERVICE_VERSION,
        status="reconciled_retain_only",
        reason_codes=["IV_RECOVERY_RECONCILED_NOT_EXECUTION_AUTHORIZATION"],
        stage_build_id="a" * 64,
        expected_stage_fingerprint="b" * 64,
        inventory_before_fingerprint="c" * 64,
        inventory_after_fingerprint="c" * 64,
        evidence_fingerprint="d" * 64,
        stage_recording_checked=True,
        entries=[dict(name_sha256="e" * 64, disposition="RECORDED_ARTIFACT_RETAIN")],
    )
    return value


def test_round_trip_complete_plan_and_exact_bytes():
    value = body()
    raw = record.encode("C:/synthetic/root", value)
    assert record.decode(raw)["plan"] == value
    assert record.encode("C:/synthetic/root", record.decode(raw)["plan"]) == raw
    assert len(record.sha(raw.encode())) == 64


@pytest.mark.parametrize("field", record.DENIALS)
def test_authority_escalation_rejected(field):
    value = body()
    value[field] = True
    with pytest.raises(ValueError, match="RESEARCH_PLAN_REQUIRED"):
        record.encode("synthetic", value)


@pytest.mark.parametrize("field", record.NULLS)
def test_invented_identity_times_rejected(field):
    value = body()
    value[field] = "invented"
    with pytest.raises(ValueError):
        record.encode("synthetic", value)


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "duplicate",
        "order",
        "unknown",
        "negative-reason",
        "positive-reason",
        "pin",
        "extra",
        "bool",
        "inventory",
    ],
    ids=[
        "empty",
        "duplicate",
        "order",
        "unknown",
        "negative-reason",
        "positive-reason",
        "pin",
        "extra",
        "bool",
        "inventory",
    ],
)
def test_contract_rejections(change):
    value = body()
    if change == "empty":
        value["entries"] = []
    elif change == "duplicate":
        value["entries"] *= 2
    elif change == "order":
        value["status"] = "review_required"
        value["reason_codes"] = ["IV_RECOVERY_UNRESOLVED_ENTRIES_RETAIN"]
        value["entries"] += [
            dict(name_sha256="a" * 64, disposition="OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN")
        ]
    elif change == "unknown":
        value["entries"][0]["disposition"] = "DELETE"
    elif change == "negative-reason":
        value["reason_codes"] = ["IV_RECOVERY_EVIDENCE_CHANGED"]
    elif change == "positive-reason":
        value["status"] = "review_required"
    elif change == "pin":
        value["evidence_fingerprint"] = "A" * 64
    elif change == "extra":
        value["caller_verified"] = True
    elif change == "bool":
        value["stage_recording_checked"] = 1
    else:
        value["inventory_after_fingerprint"] = "f" * 64
    with pytest.raises(ValueError):
        record.encode("synthetic", value)


def test_review_required_is_retained_not_recast_as_positive():
    value = body()
    value["status"] = "review_required"
    value["reason_codes"] = ["IV_RECOVERY_UNRESOLVED_ENTRIES_RETAIN"]
    value["entries"].append(
        dict(name_sha256="f" * 64, disposition="OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN")
    )
    assert record.decode(record.encode("synthetic", value))["plan"] == value


def test_duplicate_noncanonical_nonfinite_and_byte_bounds(monkeypatch):
    raw = record.encode("synthetic", body())
    duplicate = raw.replace('"version":', '"version":"duplicate","version":', 1)
    for invalid in (duplicate, raw + " ", '{"version":NaN}', "not json"):
        with pytest.raises(ValueError):
            record.decode(invalid)
    monkeypatch.setattr(record, "MAX_RECORD_BYTES", len(raw.encode()) - 1)
    with pytest.raises(ValueError, match="BYTE_LIMIT"):
        record.decode(raw)


def test_every_complete_field_affects_retained_record_digest():
    original = body()
    changed = deepcopy(original)
    changed["evidence_fingerprint"] = "f" * 64
    first = record.encode("synthetic", original)
    second = record.encode("synthetic", changed)
    assert json.loads(first)["plan"] != json.loads(second)["plan"]
    assert record.sha(first.encode()) != record.sha(second.encode())
