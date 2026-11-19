"""Real DuckDB reader/graph harness; native Bronze verification is explicitly mocked."""

import json
from typing import TypedDict

import duckdb
import pytest

from nse_quant.data_platform import native_reference_reader as reader

VERSIONS = [
    "kite-native-http-reference@1",
    "kite-reference-content@1",
    "kite-native-reference-csv@1",
]
PINS = {
    "body_capture_event_id": "a" * 64,
    "body_envelope_hash": "b" * 64,
    "metadata_capture_event_id": "c" * 64,
    "metadata_envelope_hash": "d" * 64,
}

SourceVerification = tuple[
    str,
    str,
    str,
    str,
    str | None,
    str | None,
]


class ReaderHarnessState(TypedDict):
    calls: int
    current: SourceVerification | None
    code: str


@pytest.fixture
def harness(tmp_path, monkeypatch):
    conn = duckdb.connect(str(tmp_path / "silver.duckdb"))
    conn.execute("CREATE SCHEMA silver")
    table = reader._name(conn, "silver", "kite_http_reference_results")
    conn.execute(f"""CREATE TABLE {table} (
        revision_id VARCHAR,input_revision_id VARCHAR,supersedes_json VARCHAR,
        schema_version INTEGER,source_observation_id VARCHAR,body_envelope_hash VARCHAR,
        body_payload_hash VARCHAR,metadata_capture_event_id VARCHAR,metadata_envelope_hash VARCHAR,
        metadata_payload_hash VARCHAR,normalizer_version VARCHAR,content_decoder_version VARCHAR,
        csv_version VARCHAR,gate_fingerprint VARCHAR,gate_evidence_json VARCHAR,
        source_times_json VARCHAR,
        classification VARCHAR,reason_code VARCHAR,record_count INTEGER,result_json VARCHAR,
        first_job_id VARCHAR)""")
    conn.execute("CREATE SCHEMA medallion_audit")
    conn.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR,command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,state VARCHAR)"
    )
    state: ReaderHarnessState = {
        "calls": 0,
        "current": None,
        "code": "VERIFIED",
    }

    def source(_bronze, _row) -> SourceVerification:
        state["calls"] += 1

        if state["code"] != "VERIFIED":
            return (state["code"], "", "", "", None, None)

        current = state["current"]
        assert current is not None, "Seed an assessment before source verification"
        return current

    monkeypatch.setattr(reader, "_verify_source", source)

    def seed(
        label,
        *,
        supersedes=(),
        classification="normalized",
        audit="SUCCEEDED",
        tokens=(258,),
        schema=1,
    ):
        input_id = reader._hash([PINS, VERSIONS])
        gate = reader._canonical({"fixture_gate": label})
        gate_hash = reader._hash(json.loads(gate))
        revision = reader._hash([input_id, gate_hash])
        rows = (
            [
                {"row_ordinal": i, "instrument_token": token, "source_fields_hash": "e" * 64}
                for i, token in enumerate(tokens)
            ]
            if classification == "normalized"
            else []
        )
        reason = "NORMALIZED" if classification == "normalized" else "RECEIPT_CONFLICT"
        result = reader._canonical(
            {"classification": classification, "reason_code": reason, "rows": rows}
        )
        times = reader._canonical({"fixture_receipt": "2026-01-01T00:00:00+00:00"})
        job = "job-" + label
        values = [
            revision,
            input_id,
            reader._canonical(supersedes),
            schema,
            PINS["body_capture_event_id"],
            PINS["body_envelope_hash"],
            "1" * 64,
            PINS["metadata_capture_event_id"],
            PINS["metadata_envelope_hash"],
            "2" * 64,
            *VERSIONS,
            gate_hash,
            gate,
            times,
            classification,
            reason,
            len(rows),
            result,
            job,
        ]
        conn.execute(f"INSERT INTO {table} VALUES (" + ",".join(["?"] * 21) + ")", values)
        conn.execute(
            "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
            [
                job,
                "normalize.kite_native_reference@1",
                "sha256:" + input_id,
                reader._hash(VERSIONS),
            ],
        )
        conn.execute("INSERT INTO medallion_audit.job_events VALUES (?,3,?)", [job, audit])
        state["current"] = ("VERIFIED", gate, times, result, "1" * 64, "2" * 64)
        return revision

    try:
        yield conn, table, seed, state
    finally:
        conn.close()


def lookup(conn, revision, token=258):
    return reader.lookup_native_reference(
        object(), conn, assessment_revision_id=revision, instrument_token=token
    )


def test_unique_exact_row_evidence_without_publication(harness):
    conn, _, seed, state = harness
    revision = seed("one")
    result = lookup(conn, revision)
    assert result.status == "matched" and len(result.candidates) == 1
    assert result.candidates[0].assessment_revision_id == revision
    assert result.candidates[0].row_ordinal == 0
    assert result.canonical_contract_id is None
    assert not result.publication_asserted and not result.historical_validity_asserted
    assert state["calls"] == 1


def test_duplicate_token_rows_are_ambiguous(harness):
    conn, _, seed, _ = harness
    revision = seed("duplicates", tokens=(258, 258))
    result = lookup(conn, revision)
    assert result.status == "ambiguous" and len(result.candidates) == 2


def test_missing_token_has_no_fallback(harness):
    conn, _, seed, _ = harness
    revision = seed("one")
    assert lookup(conn, revision, 999).reason_code == "TOKEN_NOT_IN_PINNED_ASSESSMENT"


@pytest.mark.parametrize("audit", ["SUCCEEDED", "FAILED", "RUNNING"])
def test_quarantine_supersedes_before_quality_or_audit_filter(harness, audit):
    conn, _, seed, state = harness
    older = seed("old")
    newer = seed("quarantine", supersedes=(older,), classification="quarantine", audit=audit)
    result = lookup(conn, older)
    assert result.reason_code == "ASSESSMENT_SUPERSEDED"
    assert result.active_revision_ids == (newer,) and not result.candidates
    assert state["calls"] == 0
    head = lookup(conn, newer)
    expected = (
        "ASSESSMENT_NOT_NORMALIZED" if audit == "SUCCEEDED" else "NORMALIZATION_AUDIT_NOT_VERIFIED"
    )
    assert head.reason_code == expected and not head.candidates
    assert state["calls"] == 0


def test_unsupported_superseder_not_discarded(harness):
    conn, _, seed, state = harness
    older = seed("old")
    newer = seed("unsupported", supersedes=(older,), schema=2)
    assert lookup(conn, older).reason_code == "ASSESSMENT_SUPERSEDED"
    assert lookup(conn, newer).reason_code == "UNSUPPORTED_ASSESSMENT_SCHEMA"
    assert state["calls"] == 0


def test_source_changed_without_new_silver_assessment(harness):
    conn, _, seed, state = harness
    revision = seed("old")
    state["code"] = "SOURCE_RECEIPT_CONFLICT"
    assert lookup(conn, revision).reason_code == "SOURCE_RECEIPT_CONFLICT"


def test_ambiguous_branches_block_instead_of_latest_good(harness):
    conn, _, seed, state = harness
    older = seed("old")
    seed("branch", supersedes=(older,))
    other = seed("other", supersedes=(older,))
    assert lookup(conn, other).reason_code == "AMBIGUOUS_ACTIVE_ASSESSMENTS"
    assert state["calls"] == 0


def test_tampered_stored_content_blocked(harness):
    conn, table, seed, _ = harness
    revision = seed("one")
    conn.execute(f"UPDATE {table} SET result_json='{{}}' WHERE revision_id=?", [revision])
    assert lookup(conn, revision).reason_code == "SOURCE_ASSESSMENT_CONTENT_MISMATCH"


def test_missing_pin_and_invalid_provider_token(harness):
    conn, _, seed, state = harness
    seed("one")
    assert lookup(conn, "f" * 64).reason_code == "ASSESSMENT_NOT_FOUND"
    with pytest.raises(ValueError):
        lookup(conn, "a" * 64, True)
    assert state["calls"] == 0


def test_missing_db_cli(tmp_path, capsys):
    from nse_quant.data_platform.native_reference_reader_cli import main

    args = [
        "--bronze-db",
        str(tmp_path / "absent-bronze.duckdb"),
        "--silver-db",
        str(tmp_path / "absent-silver.duckdb"),
        "--assessment-revision-id",
        "a" * 64,
        "--instrument-token",
        "258",
    ]
    assert main(args) == 1 and not list(tmp_path.iterdir())
    assert "REFERENCE_LOOKUP_FAILED" in capsys.readouterr().out


def test_result_size_limit_before_source_revalidation(harness, monkeypatch):
    conn, _, seed, state = harness
    revision = seed("one")
    monkeypatch.setattr(reader, "MAX_RESULT_BYTES", 1)
    assert lookup(conn, revision).reason_code == "ASSESSMENT_RESOURCE_LIMIT"
    assert state["calls"] == 0


def test_history_cap_no_quality_fallback(harness, monkeypatch):
    conn, _, seed, state = harness
    older = seed("one")
    newer = seed("two", supersedes=(older,), classification="quarantine")
    monkeypatch.setattr(reader, "MAX_ASSESSMENTS", 1)
    assert lookup(conn, newer).reason_code == "ASSESSMENT_HISTORY_LIMIT"
    assert state["calls"] == 0


def test_candidate_limit_does_not_return_partial_mapping(harness, monkeypatch):
    conn, _, seed, _ = harness
    revision = seed("many", tokens=(258, 258, 258))
    monkeypatch.setattr(reader, "MAX_TOKEN_CANDIDATES", 2)
    result = lookup(conn, revision)
    assert result.reason_code == "TOKEN_CANDIDATE_LIMIT" and not result.candidates
