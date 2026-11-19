"""Real DuckDB evidence fixtures; no decoder or connection mocks."""

import hashlib
import json
import struct
from dataclasses import asdict
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.kite_decoder import DECODER_VERSION, decode
from nse_quant.data_platform.kite_frame_reader import read_kite_frame

T = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_PAYLOAD = struct.pack(">HHII", 1, 8, 257, 12345)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.astimezone(UTC).isoformat(),
    )


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def evidence():
    bronze = duckdb.connect(":memory:")
    silver = duckdb.connect(":memory:")
    bronze.execute("CREATE SCHEMA bronze")
    bronze.execute(
        "CREATE TABLE bronze.event_variants (capture_event_id VARCHAR, "
        "envelope_hash VARCHAR,payload BLOB,payload_hash VARCHAR,envelope_json VARCHAR,"
        "received_at TIMESTAMPTZ,recorded_at TIMESTAMPTZ,source VARCHAR,"
        "payload_format VARCHAR,capture_session_id VARCHAR,source_record_id VARCHAR,"
        "origin_kind VARCHAR)"
    )
    silver.execute("CREATE SCHEMA silver")
    silver.execute("CREATE SCHEMA medallion_audit")
    silver.execute("CREATE TABLE silver.kite_schema_versions (version INTEGER)")
    silver.execute("INSERT INTO silver.kite_schema_versions VALUES (1)")
    silver.execute(
        "CREATE TABLE silver.kite_frames (revision_id VARCHAR,"
        "source_observation_id VARCHAR,envelope_hash VARCHAR,payload_hash VARCHAR,"
        "decoder_version VARCHAR,received_at TIMESTAMPTZ,bronze_recorded_at TIMESTAMPTZ,"
        "classification VARCHAR,reason_code VARCHAR,result_json VARCHAR,job_id VARCHAR)"
    )
    silver.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR,command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR)"
    )
    silver.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,state VARCHAR)"
    )

    def populate(payload=DEFAULT_PAYLOAD, fmt="kite_ws_binary_payload"):
        for connection, tables in (
            (bronze, ["bronze.event_variants"]),
            (silver, ["silver.kite_frames", "medallion_audit.jobs", "medallion_audit.job_events"]),
        ):
            for table in tables:
                connection.execute(f"DELETE FROM {table}")
        ph = digest(payload)
        env = {
            "envelope_version": 1,
            "source": "kite_websocket",
            "capture_session_id": "s1",
            "source_record_id": "frame-000000000001",
            "received_at": T.isoformat(),
            "payload_hash": ph,
            "payload_format": fmt,
            "origin_kind": "live_provider",
            "exchange_ts": None,
            "provider_event_id": None,
            "instrument_ref": None,
        }
        ej = canonical(env)
        eh = digest(ej.encode())
        event = digest(
            canonical([env["source"], env["capture_session_id"], env["source_record_id"]]).encode()
        )
        revision = digest(canonical([event, eh, ph, DECODER_VERSION]).encode())
        bronze.execute(
            "INSERT INTO bronze.event_variants VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                event,
                eh,
                payload,
                ph,
                ej,
                T,
                T,
                env["source"],
                fmt,
                "s1",
                env["source_record_id"],
                "live_provider",
            ],
        )
        result = decode(payload, fmt)
        silver.execute(
            "INSERT INTO silver.kite_frames VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                revision,
                event,
                eh,
                ph,
                DECODER_VERSION,
                T,
                T,
                result.classification,
                result.reason_code,
                canonical(asdict(result)),
                "job1",
            ],
        )
        silver.execute(
            "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
            [
                "job1",
                "normalize.kite_binary@1",
                "sha256:" + revision,
                digest(DECODER_VERSION.encode()),
            ],
        )
        silver.execute("INSERT INTO medallion_audit.job_events VALUES ('job1',1,'SUCCEEDED')")
        return revision

    revision = populate()
    yield bronze, silver, revision, populate
    bronze.close()
    silver.close()


def test_verified_frame_preserves_packet_and_unknown_times(evidence):
    b, s, revision, _ = evidence
    result = read_kite_frame(b, s, revision_id=revision)
    assert result.status == "verified"
    assert result.decoded.packets[0].instrument_token == 257
    assert result.decoded.packets[0].exchange_event_time is None
    assert result.publication_asserted is False
    assert result.historical_validity_asserted is False
    assert result.decision_eligibility_asserted is False
    assert read_kite_frame(b, s, revision_id=revision) == result


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE silver.kite_frames SET result_json='{}'", "FRAME_DECODE_CONTENT_MISMATCH"),
        ("UPDATE silver.kite_frames SET classification='fake'", "FRAME_DECODE_CONTENT_MISMATCH"),
        (
            "UPDATE silver.kite_frames SET decoder_version='kite-binary@999'",
            "UNSUPPORTED_FRAME_DECODER",
        ),
        ("UPDATE silver.kite_frames SET payload_hash=repeat('b',64)", "FRAME_REVISION_MISMATCH"),
        ("UPDATE medallion_audit.jobs SET scope_ref='bad'", "NORMALIZATION_AUDIT_NOT_VERIFIED"),
        ("UPDATE medallion_audit.jobs SET config_hash='bad'", "NORMALIZATION_AUDIT_NOT_VERIFIED"),
        ("DELETE FROM medallion_audit.jobs", "NORMALIZATION_AUDIT_NOT_VERIFIED"),
        (
            "INSERT INTO medallion_audit.job_events VALUES ('job1',2,'FAILED')",
            "NORMALIZATION_AUDIT_NOT_VERIFIED",
        ),
        ("UPDATE silver.kite_schema_versions SET version=2", "UNSUPPORTED_FRAME_SCHEMA"),
        ("UPDATE silver.kite_frames SET result_json=repeat('x',16777217)", "FRAME_RESULT_LIMIT"),
    ],
)
def test_silver_tampering_blocks(evidence, sql, expected):
    b, s, revision, _ = evidence
    s.execute(sql)
    result = read_kite_frame(b, s, revision_id=revision)
    assert result.reason_code == expected
    assert result.status == "blocked"
    assert result.decoded is None


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE bronze.event_variants SET payload='corrupt'::BLOB", "BRONZE_INTEGRITY_FAILURE"),
        (
            "UPDATE bronze.event_variants SET capture_session_id='changed'",
            "BRONZE_INTEGRITY_FAILURE",
        ),
        (
            "UPDATE bronze.event_variants SET envelope_json='{}'",
            "BRONZE_ENVELOPE_CONTRACT_MISMATCH",
        ),
        ("UPDATE bronze.event_variants SET envelope_json='not-json'", "MALFORMED_FRAME_EVIDENCE"),
        (
            "UPDATE bronze.event_variants SET received_at=received_at+INTERVAL 1 SECOND",
            "FRAME_SOURCE_TIME_MISMATCH",
        ),
        (
            "UPDATE bronze.event_variants SET recorded_at=recorded_at+INTERVAL 1 SECOND",
            "FRAME_SOURCE_TIME_MISMATCH",
        ),
        ("DELETE FROM bronze.event_variants", "PINNED_BRONZE_VARIANT_NOT_FOUND"),
        (
            "UPDATE bronze.event_variants SET payload=encode(repeat('x',1048577))",
            "BRONZE_RESOURCE_LIMIT",
        ),
        (
            "INSERT INTO bronze.event_variants SELECT capture_event_id,repeat('c',64),payload,"
            "payload_hash,envelope_json,received_at,recorded_at,source,payload_format,"
            "capture_session_id,source_record_id,origin_kind FROM bronze.event_variants",
            "BRONZE_RECEIPT_CONFLICT",
        ),
    ],
)
def test_bronze_tampering_blocks(evidence, sql, expected):
    b, s, revision, _ = evidence
    b.execute(sql)
    assert read_kite_frame(b, s, revision_id=revision).reason_code == expected


@pytest.mark.parametrize(
    "payload,fmt,classification",
    [
        (b"x", "kite_ws_binary_payload", "heartbeat_control"),
        (b"", "kite_ws_binary_payload", "quarantine"),
        (b"opaque", "kite_ws_text_reencoded_utf8", "text_notification"),
        (b"opaque", "unknown", "unsupported"),
        (struct.pack(">HHII", 1, 8, 257, 100) + b"extra", "kite_ws_binary_payload", "quarantine"),
    ],
)
def test_nonquote_evidence_is_verified_without_salvage(evidence, payload, fmt, classification):
    b, s, _, populate = evidence
    revision = populate(payload, fmt)
    result = read_kite_frame(b, s, revision_id=revision)
    assert result.status == "verified"
    assert result.decoded.classification == classification
    assert result.decoded.packets == ()


def test_missing_frame(evidence):
    b, s, _, _ = evidence
    assert read_kite_frame(b, s, revision_id="f" * 64).reason_code == "FRAME_NOT_FOUND"


@pytest.mark.parametrize("pin", ["", "A" * 64, "f" * 63])
def test_invalid_revision_rejected(evidence, pin):
    b, s, _, _ = evidence
    with pytest.raises(ValueError, match="EXACT_FRAME_REVISION_REQUIRED"):
        read_kite_frame(b, s, revision_id=pin)


def test_same_connection_rejected(evidence):
    b, _, revision, _ = evidence
    with pytest.raises(ValueError, match="SEPARATE_DATABASES_REQUIRED"):
        read_kite_frame(b, b, revision_id=revision)


@pytest.mark.parametrize("size,token", [(28, 265), (32, 265), (44, 257), (184, 257)])
def test_supported_quote_and_full_layouts(evidence, size, token):
    b, s, _, populate = evidence
    raw = struct.pack(">II", token, 12345) + bytes(size - 8)
    revision = populate(struct.pack(">HH", 1, size) + raw)
    result = read_kite_frame(b, s, revision_id=revision)
    assert result.status == "verified"
    assert result.decoded is not None
    assert result.decoded.packets[0].size == size
    assert result.decoded.packets[0].payload_offset == 4
    assert result.decoded.packets[0].exchange_event_time is None


def test_real_read_only_files_and_quoted_catalogs(evidence, tmp_path):
    b, s, revision, _ = evidence
    paths = [tmp_path / "bronze.quoted'name.duckdb", tmp_path / "silver.quoted'name.duckdb"]
    connections = []
    for original, path in zip((b, s), paths, strict=True):
        escaped = str(path).replace("'", "''")
        original.execute(f"ATTACH '{escaped}' AS export_target")
        original.execute("COPY FROM DATABASE memory TO export_target")
        original.execute("DETACH export_target")
    before = [digest(path.read_bytes()) for path in paths]
    try:
        connections = [duckdb.connect(str(path), read_only=True) for path in paths]
        result = read_kite_frame(*connections, revision_id=revision)
        assert result.status == "verified"
    finally:
        for connection in connections:
            connection.close()
    assert [digest(path.read_bytes()) for path in paths] == before
