"""Pure full-context contracts; no native source/JSON-column attestation claim."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.data_platform import legacy_evidence_snapshot_silver_store as store

AT = datetime(2026, 1, 1, 9, 15, 0, 123456, tzinfo=UTC)
OPAQUE = 'not-json {"eligible":true,"eligible":false}'


def context(payload=OPAQUE, symbol=None):
    row = ["R", AT.isoformat(), symbol, "P", payload]
    snapshot = store.codec.make_snapshot("fixture", [row])
    pins = store.EvidenceSnapshotBronzePins(
        "fixture", snapshot.snapshot_id, "a" * 64, "b" * 64, "c" * 64
    )
    return pins, store._context(pins, snapshot.payload)


def test_full_context_and_aware_scalar_replay_payload_not_parsed():
    pins, raw = context()
    checked, rows = store._derive(raw)
    assert checked == pins
    assert len(rows) == 1
    values = store._values(rows[0])
    assert values[2:] == ("R", AT, None, "P", OPAQUE)
    assert values[3].tzinfo is not None
    doc = store.codec.parse(rows[0], store.MAX_RECORD)
    assert doc["stored_ts_instant"] == AT.isoformat()
    assert doc["original_availability_at"] is None
    assert not doc["payload_interpreted"]
    assert not doc["payload_json_validation_reperformed"]
    assert not doc["native_decision_replayed"]
    assert not doc["decision_eligibility_asserted"]


def test_sql_null_and_json_null_text_are_distinct():
    _pins, absent = context(None)
    _pins, literal = context("null")
    assert absent != literal
    assert store._values(store._derive(absent)[1][0])[-1] is None
    assert store._values(store._derive(literal)[1][0])[-1] == "null"


def test_symbol_null_and_empty_are_distinct():
    _pins, null = context(symbol=None)
    _pins, empty = context(symbol="")
    assert null != empty
    assert store._values(store._derive(null)[1][0])[-3] is None
    assert store._values(store._derive(empty)[1][0])[-3] == ""


@pytest.mark.parametrize(
    "field",
    ["source_label", "snapshot_id", "envelope_hash", "recording_fingerprint"],
    ids=["label", "snapshot", "envelope", "recording"],
)
def test_review_pin_changes_do_not_create_healable_scope(field):
    pins, _raw = context()
    changed = replace(pins, **{field: "other" if field == "source_label" else "d" * 64})
    assert changed.scope_id == pins.scope_id


@pytest.mark.parametrize(
    "field",
    ["version", "snapshot_hex", "pins", "extra"],
    ids=["version", "snapshot", "pins", "extra"],
)
def test_context_corruption_even_if_rehashed(field):
    _pins, raw = context()
    doc = store.codec.parse(raw, store.MAX_CONTEXT)
    if field == "extra":
        doc[field] = True
    elif field == "pins":
        doc[field]["snapshot_id"] = "0" * 64
    else:
        doc[field] = "bad"
    with pytest.raises(ValueError):
        store._derive(store.codec.canonical(doc))


@pytest.mark.parametrize("kind", ["space", "uppercase", "odd"], ids=["space", "uppercase", "odd"])
def test_context_hex_not_lenient(kind):
    _pins, raw = context()
    doc = store.codec.parse(raw, store.MAX_CONTEXT)
    if kind == "space":
        doc["snapshot_hex"] += " "
    elif kind == "uppercase":
        doc["snapshot_hex"] = doc["snapshot_hex"].upper()
    else:
        doc["snapshot_hex"] = doc["snapshot_hex"][:-1]
    with pytest.raises(ValueError, match="HEX_BOUND"):
        store._derive(store.codec.canonical(doc))


def test_duplicate_key_cannot_be_hidden_with_different_symbol():
    row = ["R", AT.isoformat(), "S", "P", None]
    with pytest.raises(ValueError, match="DUPLICATE"):
        store.codec.make_snapshot("fixture", [row, [*row[:2], "other", *row[3:]]])


def test_aware_instant_codec_and_naive_refusal_remain_distinct():
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert store.codec.encode_cell(local, "TIMESTAMP WITH TIME ZONE") == AT.isoformat()
    with pytest.raises(ValueError, match="AWARE"):
        store.codec.encode_cell(datetime(2026, 1, 1), "TIMESTAMP WITH TIME ZONE")


def test_context_bound_before_parse():
    with pytest.raises(ValueError):
        store._derive(b"x" * (store.MAX_CONTEXT + 1))


def test_pin_and_request_type_gates():
    with pytest.raises(ValueError):
        store.EvidenceSnapshotBronzePins("fixture", "bad", "a" * 64, "b" * 64, "c" * 64)
    with pytest.raises(ValueError, match="TYPED"):
        store._pins({})
