"""Pure retained gate contracts, not SQL-source, execution or native approval attestation."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.data_platform import legacy_gate_results as codec

AT = datetime(2026, 1, 1, 9, 15, 0, 123456, tzinfo=UTC)
OPAQUE = 'not-json {"passed":true,"eligible":true,"eligible":false}'


def row(**changes):
    fields = dict(
        gate_result_id="G",
        ts=AT.isoformat(),
        run_id="R",
        proposal_id=None,
        strategy="S",
        gate="gate",
        passed=True,
        reason=OPAQUE,
        details=OPAQUE,
    )
    fields.update(changes)
    return [fields[n] for n, _kind in codec.SCHEMA]


def test_full_projection_retains_pass_claim_and_opaque_text_without_approval():
    snapshot = codec.make_snapshot("fixture", [row()])
    raw = codec.derive_records(
        snapshot.payload,
        snapshot_id=snapshot.snapshot_id,
        capture_event_id="a" * 64,
        envelope_hash="b" * 64,
    )[0]
    doc = codec.parse(raw, codec.MAX_RECORD)
    assert doc["stored_fields"]["passed"] is True
    assert doc["stored_fields"]["reason"] == doc["stored_fields"]["details"] == OPAQUE
    assert not doc["decision_eligibility_asserted"]
    assert not doc["original_gate_execution_replayed"]
    assert not doc["details_interpreted"]
    assert not doc["details_json_revalidated"]  # Pure opaque text is not JSON-column proof.


@pytest.mark.parametrize("passed", [True, False, None], ids=["true", "false", "unknown"])
def test_nullable_boolean_distinct(passed):
    original = row(passed=passed)
    s = codec.make_snapshot("fixture", [original])
    assert codec.replay_snapshot(s.payload, expected_snapshot_id=s.snapshot_id)["rows"] == [
        original
    ]


@pytest.mark.parametrize(
    "value",
    [0, 1, "true", "false", [], {}],
    ids=["int-zero", "int-one", "str-true", "str-false", "array", "object"],
)
def test_boolean_not_coerced(value):
    with pytest.raises(ValueError):
        codec.make_snapshot("fixture", [row(passed=value)])


def test_all_nonkey_fields_nullable_and_no_natural_key_invented():
    a = ["A", *([None] * 8)]
    b = ["B", *([None] * 8)]
    snapshot = codec.make_snapshot("fixture", [b, a])
    assert codec.replay_snapshot(snapshot.payload, expected_snapshot_id=snapshot.snapshot_id)[
        "rows"
    ] == [a, b]
    with pytest.raises(ValueError, match="DUPLICATE"):
        codec.make_snapshot("fixture", [a, list(a)])
    with pytest.raises(ValueError, match="KEY_UNKNOWN"):
        codec.make_snapshot("fixture", [[None, *a[1:]]])


def test_sql_null_json_null_text_and_empty_are_distinct():
    snapshots = [codec.make_snapshot("fixture", [row(details=v)]) for v in (None, "null", "")]
    assert len({s.snapshot_id for s in snapshots}) == 3


def test_nullable_instant_does_not_invent_availability():
    s = codec.make_snapshot("fixture", [row(ts=None)])
    raw = codec.derive_records(
        s.payload, snapshot_id=s.snapshot_id, capture_event_id="a" * 64, envelope_hash="b" * 64
    )[0]
    doc = codec.parse(raw, codec.MAX_RECORD)
    assert doc["stored_ts_instant"] is None
    assert doc["original_availability_at"] is None


def test_aware_utc_normalization_and_naive_refusal():
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert codec.encode_cell(local, "TIMESTAMP WITH TIME ZONE") == AT.isoformat()
    with pytest.raises(ValueError, match="AWARE"):
        codec.encode_cell(datetime(2026, 1, 1), "TIMESTAMP WITH TIME ZONE")
    with pytest.raises(ValueError, match="CANONICAL"):
        codec.make_snapshot("fixture", [row(ts=local.isoformat())])


@pytest.mark.parametrize("count", [0, 1001], ids=["empty", "overflow"])
def test_complete_row_bound(count):
    with pytest.raises(ValueError, match="ROW_BOUND"):
        codec.make_snapshot("fixture", [row()] * count)


@pytest.mark.parametrize(
    "field", ["reason", "details", "gate_result_id"], ids=["reason", "details", "id"]
)
def test_text_cell_bound(field):
    with pytest.raises(ValueError, match="CELL_BOUND"):
        codec.make_snapshot("fixture", [row(**{field: "x" * 65537})])


def test_outer_duplicate_unknown_keys_and_checksum_not_payload_interpretation():
    s = codec.make_snapshot("fixture", [row()])
    doc = codec.parse(s.payload, codec.MAX_BYTES)
    doc["extra"] = True
    changed = codec.canonical(doc)
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        codec.replay_snapshot(changed, expected_snapshot_id=codec.sha(changed))
    duplicate = b'{"x":1,"x":2}'
    with pytest.raises(ValueError, match="DUPLICATE"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))
    with pytest.raises(ValueError, match="PIN"):
        codec.replay_snapshot(s.payload, expected_snapshot_id="0" * 64)


def test_projection_bound_is_independent_of_snapshot_bound():
    r = row(
        gate_result_id="g" * 65536,
        run_id="r" * 65536,
        proposal_id="p" * 65536,
        strategy="s" * 65536,
        gate="q" * 65536,
        reason="x" * 65536,
        details="\x01" * 65536,
    )
    s = codec.make_snapshot("fixture", [r])
    assert len(s.payload) <= codec.MAX_BYTES
    with pytest.raises(ValueError, match="PROJECTION_BYTE_BOUND"):
        codec.derive_records(
            s.payload, snapshot_id=s.snapshot_id, capture_event_id="a" * 64, envelope_hash="b" * 64
        )


def test_raw_bytes_bound_before_outer_parse():
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        codec.replay_snapshot(b"x" * (codec.MAX_BYTES + 1), expected_snapshot_id="a" * 64)
