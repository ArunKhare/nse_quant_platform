"""Pure partition Silver content tests; never counted as native source attestation."""

import json
from dataclasses import replace
from typing import Any

import pytest

from nse_quant.data_platform import legacy_market_partition_silver as codec
from nse_quant.data_platform import legacy_market_partitions as partitions
from nse_quant.data_platform import legacy_market_snapshot as snapshot


def example(count=1, table="spot_candles", **changes):
    names = tuple(n for n, _kind in snapshot.SCHEMAS[table])
    rows = []
    for i in range(count):
        fields: dict[str, Any] = dict.fromkeys(names)
        fields.update(
            instrument_token=str(i + 1), ts="2026-01-01T00:00:00+00:00", volume="0", oi=None
        )
        if table == "spot_candles":
            fields.update(symbol="SYNTHETIC", interval="1m", open=(-0.0).hex())
        else:
            fields.update(run_id="synthetic", iv=(0.2).hex(), payload_json=' {"x": 0} ')
        fields.update(changes)
        rows.append(tuple(fields[n] for n in names))
    capture = partitions.make_partition_capture(
        table=table, source_label="synthetic", schema=snapshot.SCHEMAS[table], rows=tuple(rows)
    )
    pins = codec.PartitionBronzePins(capture.capture_id, table, "synthetic", "a" * 64)
    return capture, pins


@pytest.mark.parametrize("count", [1, 1000, 1001, 16000], ids=["one", "part", "two", "max"])
def test_complete_global_local_lineage(count):
    capture, pins = example(count)
    records = codec.derive_partition_records(capture.artifact, pins=pins)
    manifest = json.loads(capture.manifest)
    assert len(records) == manifest["row_count"] == count
    for ordinal, raw in enumerate(records):
        body = json.loads(raw)
        index, local = divmod(ordinal, 1000)
        assert body["source_ordinal"] == ordinal
        assert body["partition_index"] == index
        assert body["partition_ordinal"] == local
        assert body["partition_payload_sha256"] == manifest["partitions"][index]["payload_sha256"]
        assert body["stored_fields"]["volume"] == "0"
        assert body["stored_fields"]["oi"] is None
        assert body["decision_eligibility_asserted"] is False
        assert body["canonical_contract_id"] is None


@pytest.mark.parametrize("table", ["spot_candles", "option_stream"], ids=["candles", "options"])
def test_exact_values_no_recomputation(table):
    capture, pins = example(table=table)
    record = json.loads(codec.derive_partition_records(capture.artifact, pins=pins)[0])
    if table == "option_stream":
        assert record["legacy_derived_fields"]["iv"] == (0.2).hex()
        assert record["stored_fields"]["payload_json"] == ' {"x": 0} '
    else:
        assert record["stored_fields"]["open"] == (-0.0).hex()
    assert record["availability_evidence_verified"] is False
    assert record["economic_validity_verified"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", "nan"),
        ("open", "1.0"),
        ("volume", "01"),
        ("oi", str(2**63)),
        ("ts", "2026-01-01T00:00:00"),
        ("ts", "2026-01-01T05:30:00+05:30"),
    ],
    ids=["nan", "decimal", "integer", "overflow", "naive", "offset"],
)
def test_scalar_validation_not_only_partition_hash(field, value):
    capture, pins = example(**{field: value})
    with pytest.raises(ValueError):
        codec.derive_partition_records(capture.artifact, pins=pins)


@pytest.mark.parametrize(
    "case",
    ["missing", "repeat", "reorder", "gap", "overlap", "mixed"],
    ids=["missing", "repeat", "reorder", "gap", "overlap", "mixed"],
)
def test_rehashed_incomplete_or_mixed_coverage_refused(case):
    capture, pins = example(1001)
    envelope = json.loads(capture.artifact)
    payloads = envelope["partitions_hex"]
    if case == "missing":
        payloads.pop()
    elif case == "repeat":
        payloads[1] = payloads[0]
    elif case == "reorder":
        payloads.reverse()
    else:
        part = json.loads(bytes.fromhex(payloads[1]))
        if case == "gap":
            part["first_ordinal"] += 1
        elif case == "overlap":
            part["first_ordinal"] -= 1
        else:
            part["source_label"] = "other"
        payloads[1] = codec.canonical(part).hex()
    raw = codec.canonical(envelope)
    pins = replace(pins, capture_id=codec.sha(raw))
    with pytest.raises(ValueError):
        codec.derive_partition_records(raw, pins=pins)


def test_wrong_subject_and_recording_pin_binding():
    capture, pins = example()
    with pytest.raises(ValueError, match="SUBJECT"):
        codec.derive_partition_records(capture.artifact, pins=replace(pins, source_label="other"))
    other = replace(pins, recording_fingerprint="b" * 64)
    assert pins.scope_id == other.scope_id
    assert codec.derive_partition_records(capture.artifact, pins=pins) != (
        codec.derive_partition_records(capture.artifact, pins=other)
    )


def test_typed_pins_not_successful_dto():
    capture, _pins = example()
    untyped: Any = {}
    with pytest.raises(ValueError, match="TYPED"):
        codec.derive_partition_records(capture.artifact, pins=untyped)


def test_limits_leave_old_profiles_unchanged():
    from nse_quant.data_platform import legacy_market_silver as old

    assert old.MAX_ROWS == 1000
    assert old.MAX_SET_BYTES == 8388608
    assert codec.partitions.MAX_ROWS == 16000
    assert codec.MAX_RECORD_TOTAL_BYTES == 33554432


def test_actual_oversized_cell_short_parameter_id():
    with pytest.raises(ValueError, match="SHAPE"):
        example(symbol="x" * 65537)


def test_actual_projection_aggregate_bound_from_repeated_key_lineage():
    capture, _pins = example(1000)
    rows = [list(row) for row in json.loads(capture.partitions[0])["rows"]]
    # Canonical encoded key ordering puts these already sorted endpoints at the bounds.
    rows[0][2] = "a" * 9000
    rows[-1][2] = "z" * 9000
    capture = partitions.make_partition_capture(
        table="spot_candles",
        source_label="synthetic",
        schema=snapshot.SCHEMAS["spot_candles"],
        rows=tuple(tuple(row) for row in rows),
    )
    pins = codec.PartitionBronzePins(capture.capture_id, "spot_candles", "synthetic", "a" * 64)
    assert capture.row_count == 1000
    assert len(capture.manifest) < 65536
    assert len(capture.artifact) < codec.MAX_CONTEXT_BYTES
    with pytest.raises(ValueError, match="RECORD_BYTE_BOUND"):
        codec.derive_partition_records(capture.artifact, pins=pins)
