"""Pure codec tests over untrusted synthetic bytes; not native/model/audit verification."""

from copy import deepcopy
from typing import Any

import pytest

from nse_quant.data_platform import research_iv_stress_archive_record as record

PINS = ("a" * 64, "b" * 64, "c" * 64)


def negative():
    value: dict[str, Any] = dict.fromkeys((*record.DENIALS, *record.FACTS), False)
    value.update(
        dict.fromkeys(
            (
                *record.NULLS,
                "after",
                "provisional_study",
                "repeated_study",
                "study",
                "evidence_fingerprint",
                "source_option_event_ts",
                "source_spot_event_ts",
            )
        )
    )
    value.update(
        version=record.NATIVE_VERSION,
        build_id=PINS[0],
        expected_archive_fingerprint=PINS[1],
        expected_revalidation_fingerprint=PINS[2],
        status="review_required",
        reason_codes=["SYNTHETIC_CODEC_REVIEW"],
        before={"opaque_original_observation": "preserve these bytes"},
    )
    return value


def test_complete_negative_roundtrip_retains_opaque_nested_evidence():
    value = negative()
    requested = record.request(PINS, (-1, 0, 1))
    raw = record.encode(requested, value)
    assert record.decode(raw)["result"] == value
    assert record.decode(raw)["definition"] == list(record.DEFINITION)
    assert record.decode(raw)["request"] == requested
    assert len(record.sha(raw.encode())) == 64


@pytest.mark.parametrize("field", record.DENIALS)
def test_authority_escalation_rejected(field):
    value = negative()
    value[field] = True
    with pytest.raises(ValueError):
        record.encode(record.request(PINS, (0,)), value)


@pytest.mark.parametrize("field", record.NULLS)
def test_invented_generic_identity_or_time_rejected(field):
    value = negative()
    value[field] = "invented"
    with pytest.raises(ValueError):
        record.encode(record.request(PINS, (0,)), value)


@pytest.mark.parametrize(
    "shocks",
    [(), (0,) * 17, [0], (True,), (1.0,), (-5001,), (5001,), (0, 0), (1, 0)],
    ids=["empty", "count", "list", "bool", "float", "low", "high", "duplicate", "order"],
)
def test_request_grid_bounds(shocks):
    with pytest.raises(ValueError):
        record.request(PINS, shocks)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown@2"},
        {"build_id": "d" * 64},
        {"current_source_checked": 1},
        {"evidence_fingerprint": "d" * 64},
        {"study": {}},
        {"status": "published"},
        {"reason_codes": []},
        {"reason_codes": ["DUP", "DUP"]},
        {"reason_codes": ["private text"]},
        {"extra": "private"},
    ],
    ids=[
        "version",
        "pin",
        "bool",
        "evidence",
        "study",
        "status",
        "empty",
        "duplicate",
        "reason",
        "schema",
    ],
)
def test_result_shape_and_review_boundaries(changes):
    value = negative()
    value.update(changes)
    with pytest.raises(ValueError):
        record.encode(record.request(PINS, (0,)), value)


def test_duplicate_keys_noncanonical_json_and_nonfinite_rejected():
    raw = record.encode(record.request(PINS, (0,)), negative())
    duplicate = raw.replace('"version":', '"version":"duplicate","version":', 1)
    for invalid in (duplicate, raw + " ", '{"result":NaN}', '{"result":1e999}'):
        with pytest.raises(ValueError):
            record.decode(invalid)


def test_nested_observation_and_total_record_bounds(monkeypatch):
    value = negative()
    monkeypatch.setattr(record, "MAX_NATIVE_BYTES", 1)
    with pytest.raises(ValueError, match="NATIVE_OBSERVATION_BYTE_LIMIT"):
        record.encode(record.request(PINS, (0,)), value)
    monkeypatch.setattr(record, "MAX_NATIVE_BYTES", 8388608)
    raw = record.encode(record.request(PINS, (0,)), value)
    monkeypatch.setattr(record, "MAX_RECORD_BYTES", len(raw.encode()) - 1)
    with pytest.raises(ValueError, match="RECORD_BYTE_LIMIT"):
        record.decode(raw)


def test_grid_and_retained_native_bytes_both_bind_record_identity():
    original = negative()
    changed = deepcopy(original)
    changed["before"]["opaque_original_observation"] = "different"
    first = record.encode(record.request(PINS, (0,)), original)
    second = record.encode(record.request(PINS, (0,)), changed)
    third = record.encode(record.request(PINS, (-1, 0)), original)
    assert len({record.sha(raw.encode()) for raw in (first, second, third)}) == 3
    assert record.scope(record.request(PINS, (0,))) != record.scope(record.request(PINS, (-1, 0)))


def test_incomplete_positive_never_accepted():
    value = negative()
    value["status"] = "computed_current_native_research_iv_spot_stress"
    value["evidence_fingerprint"] = "d" * 64
    value.update(dict.fromkeys(record.FACTS, True))
    value["after"] = value["before"]
    with pytest.raises(ValueError, match="INCOMPLETE_POSITIVE"):
        record.encode(record.request(PINS, (0,)), value)
