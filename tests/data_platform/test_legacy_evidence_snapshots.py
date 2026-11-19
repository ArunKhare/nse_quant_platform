"""Pure retained-table contracts, not writer/provider/decision authentication."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.data_platform import legacy_evidence_snapshots as codec

AT = datetime(2026, 1, 1, tzinfo=UTC)
OPAQUE = ' {"eligible":true,"eligible":false,"available":true} '


def row(payload=OPAQUE, symbol="S"):
    return ["R", AT.isoformat(), symbol, "P", payload]


def test_exact_payload_text_null_distinction_and_unknown_claims():
    snapshot = codec.make_snapshot(
        "fixture",
        [
            row(None),
            ["R", AT.isoformat(), None, "Q", "null"],
            ["R", AT.isoformat(), "S", "Z", OPAQUE],
        ],
    )
    records = codec.derive_records(
        snapshot.payload,
        snapshot_id=snapshot.snapshot_id,
        capture_event_id="a" * 64,
        envelope_hash="b" * 64,
    )
    docs = [codec.parse(r, codec.MAX_RECORD) for r in records]
    assert len(docs) == 3
    assert {d["stored_fields"]["payload_json"] for d in docs} == {None, "null", OPAQUE}
    assert all(not d["payload_interpreted"] for d in docs)
    assert all(not d["decision_eligibility_asserted"] for d in docs)
    assert all(not d["native_decision_replayed"] for d in docs)
    assert all(d["original_availability_at"] is None for d in docs)


def test_stored_key_excludes_nullable_symbol():
    with pytest.raises(codec.Rejected, match="DUPLICATE"):
        codec.make_snapshot("fixture", [row(symbol="A"), row(symbol="B")])


def test_stored_instant_normalizes_offset_but_encoded_rows_require_canonical_utc():
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert codec.encode_cell(local, "TIMESTAMP WITH TIME ZONE") == AT.isoformat()
    with pytest.raises(codec.Rejected):
        codec.make_snapshot("fixture", [["R", local.isoformat(), None, "P", "null"]])
    with pytest.raises(codec.Rejected):
        codec.encode_cell(datetime(2026, 1, 1), "TIMESTAMP WITH TIME ZONE")


@pytest.mark.parametrize("index", [0, 1, 3], ids=["run", "time", "plugin"])
def test_unknown_keys_reject(index):
    values = row()
    values[index] = None
    with pytest.raises(codec.Rejected, match="KEY_UNKNOWN"):
        codec.make_snapshot("fixture", [values])


def test_pure_content_codec_does_not_parse_payload_or_attest_sql_json_type():
    text = 'not-json {"available":true}'
    snapshot = codec.make_snapshot("fixture", [row(text)])
    doc = codec.replay_snapshot(snapshot.payload, expected_snapshot_id=snapshot.snapshot_id)
    assert doc["rows"][0][4] == text  # Pure shape only; native capture requires a real JSON column.


@pytest.mark.parametrize("case", ["unknown", "order", "type"], ids=["field", "row-order", "type"])
def test_complete_outer_replay(case):
    snapshot = codec.make_snapshot("fixture", [row(), ["Z", AT.isoformat(), None, "P", "null"]])
    doc = codec.parse(snapshot.payload, codec.MAX_BYTES)
    if case == "unknown":
        doc["extra"] = True
    elif case == "order":
        doc["rows"].reverse()
    else:
        doc["rows"][0][0] = True
    raw = codec.canonical(doc)
    with pytest.raises(codec.Rejected):
        codec.replay_snapshot(raw, expected_snapshot_id=codec.sha(raw))


def test_strict_outer_duplicate_keys():
    raw = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_OUTER"):
        codec.replay_snapshot(raw, expected_snapshot_id=codec.sha(raw))


@pytest.mark.parametrize("count", [0, 1001], ids=["empty", "overflow"])
def test_whole_row_bound(count):
    with pytest.raises(codec.Rejected, match="ROW_BOUND"):
        codec.make_snapshot("fixture", [row()] * count)


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["cell-limit", "cell-overflow"])
def test_text_cell_limit(text):
    if len(text) > codec.MAX_CELL:
        with pytest.raises(codec.Rejected, match="CELL_BOUND"):
            codec.make_snapshot("fixture", [row(text)])
    else:
        assert codec.make_snapshot("fixture", [row(text)]).row_count == 1


def test_snapshot_bound_before_json():
    with pytest.raises(codec.Rejected, match="BYTE_BOUND"):
        codec.parse(b"x" * (codec.MAX_BYTES + 1), codec.MAX_BYTES)


def test_projection_bound_is_independent_of_snapshot_bound():
    values = ["r" * 65536, AT.isoformat(), "\x01" * 65536, "\x01" * 65536, "null"]
    snapshot = codec.make_snapshot("fixture", [values])
    assert len(snapshot.payload) <= codec.MAX_BYTES
    with pytest.raises(codec.Rejected, match="RECORD_BYTE_BOUND"):
        codec.derive_records(
            snapshot.payload,
            snapshot_id=snapshot.snapshot_id,
            capture_event_id="a" * 64,
            envelope_hash="b" * 64,
        )
