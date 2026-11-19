"""Pure partition coverage tests; no native dependency or successful-reader substitution."""

import json

import pytest

from nse_quant.data_platform import legacy_market_partitions as codec

SCHEMA = tuple(
    (n, t)
    for n, t in zip(
        (
            "instrument_token",
            "symbol",
            "interval",
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
        ),
        (
            "BIGINT",
            "VARCHAR",
            "VARCHAR",
            "TIMESTAMP WITH TIME ZONE",
            "DOUBLE",
            "DOUBLE",
            "DOUBLE",
            "DOUBLE",
            "BIGINT",
            "BIGINT",
        ),
        strict=True,
    )
)


def rows(count):
    return tuple(
        (
            str(i + 1),
            "SYNTHETIC",
            "1m",
            "2026-01-01T00:00:00+00:00",
            (-0.0).hex(),
            (2.0).hex(),
            (0.0).hex(),
            (1.0).hex(),
            "0",
            None,
        )
        for i in range(count)
    )


def make(records):
    return codec.make_partition_capture(
        table="spot_candles", source_label="synthetic", schema=SCHEMA, rows=records
    )


@pytest.mark.parametrize("count", [1, 1000, 1001, 16000], ids=["one", "old-bound", "two", "max"])
def test_whole_coverage_and_exact_replay(count):
    value = make(rows(count))
    assert value.row_count == count
    assert (
        codec.replay_partition_capture(value.artifact, expected_capture_id=value.capture_id)
        == value
    )
    manifest = json.loads(value.manifest)
    assert sum(p["row_count"] for p in manifest["partitions"]) == count
    assert len(value.partitions) == (count + 999) // 1000
    assert manifest["decision_eligibility_asserted"] is False
    assert manifest["original_provider_bytes_retained"] is False
    decoded = [json.loads(raw) for raw in value.partitions]
    assert sum(len(p["rows"]) for p in decoded) == count
    assert all(
        r[4] == (-0.0).hex() and r[8] == "0" and r[9] is None for p in decoded for r in p["rows"]
    )


def test_physical_order_does_not_change_partition_identity():
    original = rows(1001)
    assert make(original) == make(tuple(reversed(original)))


@pytest.mark.parametrize(
    "case",
    ["empty", "overflow", "duplicate", "nullkey", "shape", "type"],
    ids=["empty", "too-many", "duplicate", "unknown-key", "shape", "type"],
)
def test_whole_capture_refusal(case):
    original = rows(1)
    if case == "empty":
        original = ()
    elif case == "overflow":
        original = rows(16001)
    elif case == "duplicate":
        original = original * 2
    else:
        row: list[object] = list(original[0])
        if case == "nullkey":
            row[0] = None
        elif case == "shape":
            row.pop()
        else:
            row[8] = True
        original = (tuple(row),)
    with pytest.raises(ValueError):
        make(original)


def test_actual_byte_splitting_not_only_row_count():
    records = tuple((r[0], "x" * 50000, *r[2:]) for r in rows(50))
    value = make(records)
    assert len(value.partitions) > 1
    assert all(len(raw) <= codec.MAX_PART_BYTES for raw in value.partitions)
    assert (
        codec.replay_partition_capture(value.artifact, expected_capture_id=value.capture_id)
        == value
    )


def test_actual_total_bytes_refuse_no_salvage():
    records = tuple((r[0], "x" * 65536, *r[2:]) for r in rows(70))
    with pytest.raises(ValueError, match="ROW_BYTE_BOUND"):
        make(records)


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "reversed",
        "duplicate",
        "manifest-count",
        "ordinal",
        "boundary",
        "cell",
        "unknown",
        "whitespace",
        "duplicate-json",
    ],
    ids=[
        "missing",
        "order",
        "duplicate",
        "count",
        "ordinal",
        "key-bound",
        "cell",
        "schema",
        "whitespace",
        "json-key",
    ],
)
def test_rehashed_coverage_and_content_tampering(case):
    value = make(rows(1001))
    envelope = json.loads(value.artifact)
    manifest = json.loads(bytes.fromhex(envelope["manifest_hex"]))
    if case == "missing":
        envelope["partitions_hex"].pop()
    elif case == "reversed":
        envelope["partitions_hex"].reverse()
    elif case == "duplicate":
        envelope["partitions_hex"][1] = envelope["partitions_hex"][0]
    elif case == "manifest-count":
        manifest["row_count"] -= 1
    elif case in ("ordinal", "boundary", "cell"):
        part = json.loads(bytes.fromhex(envelope["partitions_hex"][0]))
        if case == "ordinal":
            part["first_ordinal"] = 1
        elif case == "boundary":
            part["lower_key_hex"] = "00"
        else:
            part["rows"][0][7] = (7.0).hex()
        envelope["partitions_hex"][0] = codec.canonical(part).hex()
    elif case == "unknown":
        envelope["unknown"] = True
    envelope["manifest_hex"] = codec.canonical(manifest).hex()
    raw = codec.canonical(envelope)
    if case == "whitespace":
        raw += b" "
    if case == "duplicate-json":
        raw = raw.replace(b'"version":', b'"version":"bad","version":', 1)
    with pytest.raises(ValueError):
        codec.replay_partition_capture(raw, expected_capture_id=codec.sha(raw))


def test_wrong_reviewed_pin():
    value = make(rows(1))
    with pytest.raises(ValueError, match="PIN"):
        codec.replay_partition_capture(value.artifact, expected_capture_id="0" * 64)


def test_long_stored_key_rejected_as_manifest_bound_not_unbounded_metadata():
    schema = tuple((f"col{i}", "VARCHAR") for i in range(22))
    record: list[object] = [None] * 22
    record[0], record[1], record[7] = "x" * 65536, "ts", "257"
    with pytest.raises(ValueError, match="MANIFEST_BYTE_BOUND"):
        codec.make_partition_capture(
            table="option_stream", source_label="synthetic", schema=schema, rows=(tuple(record),)
        )
