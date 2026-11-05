"""Pure full-context/content contracts; no native recording/source-attestation substitutes."""

from dataclasses import replace
from datetime import datetime

import pytest

from nse_quant.data_platform import legacy_decision_evidence_silver as store

WALL = datetime(2026, 1, 1, 9, 15, 0, 123456)
OPAQUE = 'not-json {"available":true,"eligible":true,"eligible":false}'


def context():
    row = ["E", "R", store.codec.wall_fields(WALL), "S", "P", True, OPAQUE]
    snapshot = store.codec.make_snapshot("fixture", [row])
    pins = store.DecisionEvidenceBronzePins(
        "fixture", snapshot.snapshot_id, "a" * 64, "b" * 64, "c" * 64
    )
    return pins, store._context(pins, snapshot.payload)


def test_complete_context_and_naive_typed_scalar_replay():
    pins, raw = context()
    replayed_pins, rows = store._derive(raw)
    assert pins == replayed_pins
    assert len(rows) == 1
    values = store._values(rows[0])
    assert values[4] == WALL
    assert values[4].tzinfo is None
    assert type(values[7]) is bool and values[7] is True
    assert values[8] == OPAQUE
    doc = store.codec.parse(rows[0], store.MAX_RECORD_BYTES)
    assert doc["stored_ts_instant"] is None
    assert doc["source_timezone"] is None
    assert doc["payload_interpreted"] is False
    assert doc["decision_eligibility_asserted"] is False


def test_review_pins_excluded_from_scope_but_not_content_identity():
    pins, raw = context()
    other = replace(pins, recording_fingerprint="d" * 64, envelope_hash="e" * 64)
    assert other.scope_id == pins.scope_id
    assert replace(pins, snapshot_id="f" * 64).scope_id == pins.scope_id
    doc = store.codec.parse(raw, store.MAX_CONTEXT_BYTES)
    snapshot = bytes.fromhex(doc["snapshot_hex"])
    changed = store._context(other, snapshot)
    assert store.codec.sha(raw) != store.codec.sha(changed)


@pytest.mark.parametrize(
    "field",
    ["version", "pins", "snapshot_hex", "extra"],
    ids=["version", "pins", "snapshot", "extra"],
)
def test_context_rehashed_schema_or_content_corruption(field):
    _pins, raw = context()
    doc = store.codec.parse(raw, store.MAX_CONTEXT_BYTES)
    if field == "extra":
        doc["extra"] = True
    elif field == "pins":
        doc["pins"]["snapshot_id"] = "0" * 64
    else:
        doc[field] = "bad"
    with pytest.raises(ValueError):
        store._derive(store.codec.canonical(doc))


def test_context_bound_before_outer_json_decode():
    with pytest.raises(ValueError):
        store._derive(b"x" * (store.MAX_CONTEXT_BYTES + 1))


def test_canonical_snapshot_hex_not_lenient_hex_input():
    _pins, raw = context()
    doc = store.codec.parse(raw, store.MAX_CONTEXT_BYTES)
    doc["snapshot_hex"] += " "
    with pytest.raises(ValueError, match="HEX_BOUND"):
        store._derive(store.codec.canonical(doc))


def test_bad_pin_types_before_native_observation():
    with pytest.raises(ValueError):
        store.DecisionEvidenceBronzePins("fixture", "short", "a" * 64, "b" * 64, "c" * 64)
    with pytest.raises(ValueError, match="TYPED"):
        store._pins({})


def test_both_key_axes_remain_source_codec_obligations():
    row = ["E", "R", store.codec.wall_fields(WALL), "S", "P", False, OPAQUE]
    with pytest.raises(ValueError, match="DUPLICATE"):
        store.codec.make_snapshot("fixture", [row, ["other", *row[1:]]])
    with pytest.raises(ValueError, match="DUPLICATE"):
        store.codec.make_snapshot("fixture", [row, [row[0], "other", *row[2:]]])
