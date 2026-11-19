"""Real registry snapshots/full audit sequences; no live source verification."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_publication_reader as reader
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate

T = datetime(2026, 1, 1, tzinfo=UTC)


def digest(value):
    return hashlib.sha256(codec.canonical(value).encode()).hexdigest()


def bundle():
    value = GoldQuoteCandidate(
        "",
        codec.FEATURE_VERSION,
        "a" * 64,
        "b" * 64,
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        source_evidence_fingerprint="c" * 64,
        source_association_fingerprint="d" * 64,
        source_frame_revision_id="e" * 64,
        source_packet_ordinal=0,
        reference_assessment_revision_id="f" * 64,
        reference_row_ordinal=0,
        reference_source_fields_hash="a" * 64,
        provider_token=257,
        price_divisor=100,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
        quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
    )
    value = replace(value, build_id=digest(asdict(value)))
    raw = codec.canonical(asdict(value))
    return codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                value.build_id,
                codec.GOLD_READER_VERSION,
                "b" * 64,
                ("gold-job",),
                codec.digest(raw.encode()),
                raw,
            ),
        )
    )


@pytest.fixture
def setup(tmp_path):
    db = duckdb.connect(str(tmp_path / "publications.duckdb"))
    db.execute("CREATE SCHEMA gold")
    db.execute("CREATE SCHEMA medallion_audit")
    db.execute("CREATE TABLE gold.quote_publication_schema_versions (version INTEGER)")
    db.execute("INSERT INTO gold.quote_publication_schema_versions VALUES (1)")
    db.execute("CREATE TABLE medallion_audit.schema_versions (version INTEGER)")
    db.execute("INSERT INTO medallion_audit.schema_versions VALUES (1)")
    db.execute(
        "CREATE TABLE gold.quote_bundle_publications (build_id VARCHAR PRIMARY KEY,"
        "feature_version VARCHAR,policy_version VARCHAR,bundle_id VARCHAR,purpose VARCHAR,"
        "artifact_root VARCHAR,membership_fingerprint VARCHAR,member_count INTEGER,"
        "manifest_hash VARCHAR,manifest_byte_count BIGINT,manifest_bytes BLOB,"
        "first_stage_evidence_fingerprint VARCHAR,clock_semantics VARCHAR,"
        "event_ts TIMESTAMPTZ,"
        "published_at TIMESTAMPTZ,effective_from TIMESTAMPTZ,effective_to TIMESTAMPTZ,"
        "historical_validity_asserted BOOLEAN,decision_eligibility_asserted BOOLEAN,"
        "first_job_id VARCHAR)"
    )
    db.execute(
        "CREATE TABLE gold.quote_publication_attempts (job_id VARCHAR PRIMARY KEY,"
        "build_id VARCHAR,approved_stage_fingerprint VARCHAR,"
        "verified_stage_fingerprint VARCHAR,"
        "recorded_at TIMESTAMPTZ)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR PRIMARY KEY,command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR,actor_id VARCHAR,code_revision VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,"
        "state VARCHAR,recorded_at TIMESTAMPTZ,reason_code VARCHAR)"
    )
    db.execute(
        "CREATE TABLE medallion_audit.dataset_contracts (dataset_name VARCHAR,"
        "contract_version VARCHAR,fingerprint VARCHAR,contract_json VARCHAR)"
    )
    value = bundle()
    raw = codec.encode_quote_bundle(value)
    versions = [reader.PUBLICATION_VERSION, reader.POLICY_VERSION]
    identity = digest([versions, value.bundle_id, reader.PURPOSE])
    root_label = str(tmp_path / "absent-original-staging-root")
    contract = {
        "name": "gold.quote_bundle_publications",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_research_quote_publication",
    }
    db.execute(
        "INSERT INTO medallion_audit.dataset_contracts VALUES (?,?,?,?)",
        [contract["name"], "1", digest(contract), codec.canonical(contract)],
    )
    db.execute(
        "INSERT INTO gold.quote_bundle_publications VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            identity,
            *versions,
            value.bundle_id,
            reader.PURPOSE,
            root_label,
            value.membership_fingerprint,
            1,
            value.bundle_id,
            len(raw),
            raw,
            "c" * 64,
            reader.CLOCK_SEMANTICS,
            None,
            T,
            None,
            None,
            False,
            False,
            "job1",
        ],
    )

    def add(job="job1", states=reader.PHASES, stamp="c" * 64):
        db.execute(
            "INSERT INTO gold.quote_publication_attempts VALUES (?,?,?,?,?)",
            [job, identity, stamp, stamp, T],
        )
        db.execute(
            "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?,?,?)",
            [
                job,
                reader.COMMAND,
                "sha256:" + identity,
                digest([versions, reader.PURPOSE, root_label]),
                "test",
                "user-reviewed-version",
            ],
        )
        for index, state in enumerate(states, 1):
            db.execute(
                "INSERT INTO medallion_audit.job_events VALUES (?,?,?,?,NULL)",
                [job, index, state, T + timedelta(seconds=index)],
            )

    add()

    def run(pin=identity):
        return reader.read_research_publication(db, publication_id=pin)

    yield db, value, identity, root_label, run, add
    db.close()


def test_verified_archived_snapshot_does_not_require_original_root(setup):
    db, value, identity, root_label, run, _ = setup
    result = run()
    assert not Path(root_label).exists()
    assert result.publication_id == identity
    assert result.status == "verified_research_snapshot"
    assert result.research_publication_verified
    assert result.purpose == "RESEARCH_ONLY"
    assert result.bundle == value
    assert not result.source_current_checked
    assert not result.availability_time_known
    assert not result.historical_validity_asserted
    assert not result.decision_eligibility_asserted
    assert result.publication_recorded_at == T.isoformat()
    assert result.origin_audit_success_recorded_at == (T + timedelta(seconds=6)).isoformat()
    assert run() == result
    assert db.execute("SELECT count(*) FROM gold.quote_bundle_publications").fetchone() == (1,)


@pytest.mark.parametrize(
    "sql,reason",
    [
        (
            "UPDATE gold.quote_publication_schema_versions SET version=2",
            "UNSUPPORTED_PUBLICATION_REGISTRY_SCHEMA",
        ),
        ("DELETE FROM medallion_audit.dataset_contracts", "PUBLICATION_CONTRACT_NOT_VERIFIED"),
        (
            "UPDATE gold.quote_bundle_publications SET purpose='TRADING'",
            "UNSUPPORTED_PUBLICATION_VERSION_OR_PURPOSE",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET bundle_id=repeat('f',64)",
            "PUBLICATION_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET manifest_hash='bad'",
            "PUBLICATION_METADATA_OR_CLAIMS_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET decision_eligibility_asserted=True",
            "PUBLICATION_METADATA_OR_CLAIMS_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET effective_from=now()",
            "PUBLICATION_METADATA_OR_CLAIMS_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET member_count=2",
            "PUBLICATION_MEMBERSHIP_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET manifest_byte_count=1",
            "PUBLICATION_MANIFEST_LENGTH_MISMATCH",
        ),
        (
            "UPDATE gold.quote_bundle_publications SET published_at=NULL",
            "INVALID_PUBLICATION_RECORD_CLOCK",
        ),
        ("DELETE FROM gold.quote_publication_attempts", "PUBLICATION_ORIGIN_LINK_MISSING"),
        (
            "UPDATE gold.quote_publication_attempts SET approved_stage_fingerprint=repeat('f',64)",
            "PUBLICATION_ATTEMPT_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE medallion_audit.jobs SET config_hash='bad'",
            "PUBLICATION_ATTEMPT_IDENTITY_MISMATCH",
        ),
        ("UPDATE medallion_audit.jobs SET actor_id=''", "PUBLICATION_ATTEMPT_IDENTITY_MISMATCH"),
    ],
)
def test_metadata_and_authority_errors_block_without_snapshot(setup, sql, reason):
    db, _, _, _, run, _ = setup
    db.execute(sql)
    result = run()
    assert result.status == "blocked"
    assert result.reason_code == reason
    assert result.bundle is None
    assert not result.research_publication_verified


@pytest.mark.parametrize(
    "states,reason",
    [
        (("SUCCEEDED",), "PUBLICATION_LIFECYCLE_NOT_VERIFIED"),
        (("PLANNED", "RUNNING", "SUCCEEDED"), "PUBLICATION_LIFECYCLE_NOT_VERIFIED"),
        (
            ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "SUCCEEDED"),
            "PUBLICATION_LIFECYCLE_NOT_VERIFIED",
        ),
        (
            ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED"),
            "PUBLICATION_ATTEMPT_NOT_TERMINAL",
        ),
        (("PLANNED", "RUNNING", "FAILED"), "PUBLICATION_ORIGIN_NOT_SUCCESSFUL"),
        (
            ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "CANCELLED"),
            "PUBLICATION_LIFECYCLE_NOT_VERIFIED",
        ),
    ],
)
def test_full_lifecycle_required_not_latest_success_only(setup, states, reason):
    db, _, _, _, run, _ = setup
    db.execute("DELETE FROM medallion_audit.job_events")
    for index, state in enumerate(states, 1):
        db.execute(
            "INSERT INTO medallion_audit.job_events VALUES (?,?,?,?,NULL)",
            ["job1", index, state, T],
        )
    assert run().reason_code == reason


def test_missing_published_phase_cannot_be_hidden_by_latest_success(setup):
    db, _, _, _, run, _ = setup
    db.execute("DELETE FROM medallion_audit.job_events WHERE event_index=5")
    assert run().reason_code == "PUBLICATION_LIFECYCLE_NOT_VERIFIED"


def test_duplicate_index_and_bad_reason_are_rejected(setup):
    db, _, _, _, run, _ = setup
    db.execute(
        "INSERT INTO medallion_audit.job_events SELECT * FROM medallion_audit.job_events "
        "WHERE event_index=1"
    )
    assert run().reason_code == "PUBLICATION_LIFECYCLE_NOT_VERIFIED"
    db.execute("DELETE FROM medallion_audit.job_events WHERE event_index=1")
    db.execute(
        "INSERT INTO medallion_audit.job_events VALUES ('job1',1,'PLANNED',?,'free text')", [T]
    )
    assert run().reason_code == "PUBLICATION_LIFECYCLE_NOT_VERIFIED"


def test_pending_retry_blocks_but_does_not_erase_original_record(setup):
    db, _, _, _, run, add = setup
    add("job2", ("PLANNED", "RUNNING"))
    assert run().reason_code == "PUBLICATION_ATTEMPT_NOT_TERMINAL"
    assert db.execute("SELECT count(*) FROM gold.quote_bundle_publications").fetchone() == (1,)
    db.execute(
        "INSERT INTO medallion_audit.job_events VALUES ('job2',3,'FAILED',?,'EXECUTION_ERROR')", [T]
    )
    assert run().research_publication_verified
    assert run().successful_attempt_job_ids == ("job1",)


def test_later_success_cannot_backdate_a_failed_origin(setup):
    db, _, _, _, run, add = setup
    db.execute("UPDATE medallion_audit.job_events SET state='FAILED' WHERE event_index=6")
    add("job2")
    assert run().reason_code == "PUBLICATION_ORIGIN_NOT_SUCCESSFUL"


def test_approved_fingerprint_retries_preserve_original_clock(setup):
    _, _, _, _, run, add = setup
    add("job2", stamp="d" * 64)
    result = run()
    assert result.research_publication_verified
    assert result.publication_recorded_at == T.isoformat()
    assert result.successful_attempt_job_ids == ("job1", "job2")


def test_timezone_invariant_clock_and_fingerprint(setup):
    db, _, _, _, run, _ = setup
    db.execute("SET TimeZone='UTC'")
    first = run()
    db.execute("SET TimeZone='Asia/Kolkata'")
    assert run() == first


def test_blob_limit_and_event_limits_fail_closed(setup, monkeypatch):
    db, _, _, _, run, _ = setup
    monkeypatch.setattr(reader, "MAX_EVENTS", 1)
    assert run().reason_code == "PUBLICATION_AUDIT_BOUND_REVIEW_REQUIRED"
    monkeypatch.setattr(reader, "MAX_EVENTS", 6000)
    db.execute(
        "UPDATE gold.quote_bundle_publications SET manifest_bytes=encode(repeat('x',4194305))"
    )
    assert run().reason_code == "PUBLICATION_MANIFEST_LIMIT"


@pytest.mark.parametrize("pin", ["", "A" * 64, "a" * 63])
def test_bad_pin(setup, pin):
    _, _, _, _, run, _ = setup
    with pytest.raises(ValueError):
        run(pin)


def test_missing_publication_and_wrong_database(setup):
    db, _, _, _, run, _ = setup
    assert run("f" * 64).reason_code == "RESEARCH_PUBLICATION_NOT_FOUND"
    db.execute("CREATE TABLE option_stream (id INTEGER)")
    assert run().reason_code == "DEDICATED_PUBLICATION_REGISTRY_NOT_VERIFIED"


def test_actual_readonly_registry_named_gold_and_no_artifact_access(setup, tmp_path):
    db, _, identity, _, _, _ = setup
    path = tmp_path / "gold.duckdb"
    escaped = str(path).replace("'", "''")
    db.execute(f"ATTACH '{escaped}' AS export_target")
    db.execute("COPY FROM DATABASE publications TO export_target")
    db.execute("DETACH export_target")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    connection = duckdb.connect(str(path), read_only=True)
    try:
        assert reader.read_research_publication(
            connection, publication_id=identity
        ).research_publication_verified
    finally:
        connection.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_cli_real_archive_summary_never_exposes_feature_payload(setup, tmp_path, capsys):
    from nse_quant.data_platform.quote_publication_inspect_cli import main

    db, _, identity, _, _, _ = setup
    path = tmp_path / "inspect.duckdb"
    escaped = str(path).replace("'", "''")
    db.execute(f"ATTACH '{escaped}' AS export_target")
    db.execute("COPY FROM DATABASE publications TO export_target")
    db.execute("DETACH export_target")
    args = ["--publication-db", str(path), "--publication-id", identity, "--inspect"]
    assert main(args) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["research_publication_verified"] is True
    assert not summary["availability_time_known"]
    assert "candidate_json" not in output
    assert "123.45" not in output
    args[3] = "f" * 64
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_oversized_reason_and_missing_audit_clock_do_not_pass(setup):
    db, _, _, _, run, _ = setup
    db.execute(
        "UPDATE medallion_audit.job_events SET reason_code=repeat('A',65) WHERE event_index=6"
    )
    assert run().reason_code == "PUBLICATION_LIFECYCLE_NOT_VERIFIED"
    db.execute(
        "UPDATE medallion_audit.job_events SET reason_code=NULL,recorded_at=NULL "
        "WHERE event_index=6"
    )
    assert run().reason_code == "PUBLICATION_LIFECYCLE_NOT_VERIFIED"


def test_original_approval_cannot_be_rewritten_as_new_review(setup):
    db, _, _, _, run, _ = setup
    db.execute(
        "UPDATE gold.quote_bundle_publications SET first_stage_evidence_fingerprint=repeat('d',64)"
    )
    assert run().reason_code == "PUBLICATION_ORIGIN_NOT_SUCCESSFUL"


def test_relocated_registry_quoted_catalog_is_still_self_contained(setup, tmp_path):
    db, _, identity, _, _, _ = setup
    path = tmp_path / "archive.duckdb"
    escaped = str(path).replace("'", "''")
    alias = '"ar""ch"'
    db.execute(f"ATTACH '{escaped}' AS {alias}")
    db.execute(f"COPY FROM DATABASE publications TO {alias}")
    db.execute(f"USE {alias}")
    assert (
        reader.read_research_publication(db, publication_id=identity).status
        == "verified_research_snapshot"
    )


def test_in_memory_registry_rejected():
    with (
        duckdb.connect(":memory:") as db,
        pytest.raises(ValueError, match="FILE_BACKED_PUBLICATION_DATABASE_REQUIRED"),
    ):
        reader.read_research_publication(db, publication_id="a" * 64)
