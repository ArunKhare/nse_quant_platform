"""Real DuckDB Gold snapshots with exact-schema fixtures; source kernel substituted."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import gold_quote_reader as reader
from nse_quant.data_platform.gold_quote_features import (
    DEFINITION,
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    ExactPriceFeature,
    GoldQuoteCandidate,
)
from nse_quant.data_platform.gold_quote_store import COMMAND, STORE_VERSION

ASSESSMENT = "a" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def candidate(status="candidate"):
    value = GoldQuoteCandidate(
        "",
        FEATURE_VERSION,
        DEFINITION_FINGERPRINT,
        ASSESSMENT,
        status,
        "EXACT_PROVIDER_PRICE_FIELDS" if status == "candidate" else "SOURCE_ASSESSMENT_NOT_CURRENT",
        source_evidence_fingerprint="b" * 64 if status == "candidate" else None,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),)
        if status == "candidate"
        else (),
    )
    return replace(value, build_id=digest(asdict(value)))


@pytest.fixture
def setup(monkeypatch):
    sources = [duckdb.connect(":memory:") for _ in range(4)]
    gold = duckdb.connect(":memory:")
    gold.execute("CREATE SCHEMA gold")
    gold.execute("CREATE SCHEMA medallion_audit")
    gold.execute("CREATE TABLE gold.quote_price_schema_versions (version INTEGER PRIMARY KEY)")
    gold.execute("INSERT INTO gold.quote_price_schema_versions VALUES (1)")
    gold.execute("CREATE TABLE medallion_audit.schema_versions (version INTEGER PRIMARY KEY)")
    gold.execute("INSERT INTO medallion_audit.schema_versions VALUES (1)")
    gold.execute(
        "CREATE TABLE gold.quote_price_builds (build_id VARCHAR PRIMARY KEY,"
        "input_revision_id VARCHAR,source_assessment_revision_id VARCHAR,"
        "store_version VARCHAR,feature_version VARCHAR,definition_fingerprint VARCHAR,"
        "status VARCHAR,reason_code VARCHAR,source_evidence_fingerprint VARCHAR,"
        "result_json VARCHAR,event_ts TIMESTAMPTZ,last_trade_time TIMESTAMPTZ,"
        "published_at TIMESTAMPTZ,effective_from TIMESTAMPTZ,effective_to TIMESTAMPTZ,"
        "supersedes_json VARCHAR,recorded_at TIMESTAMPTZ,first_job_id VARCHAR)"
    )
    gold.execute(
        "CREATE TABLE gold.quote_price_definitions (feature_version VARCHAR PRIMARY KEY,"
        "definition_fingerprint VARCHAR,definition_json VARCHAR,recorded_at TIMESTAMPTZ,"
        "first_job_id VARCHAR)"
    )
    gold.execute(
        "CREATE TABLE gold.quote_price_build_attempts (job_id VARCHAR PRIMARY KEY,"
        "build_id VARCHAR,recorded_at TIMESTAMPTZ)"
    )
    gold.execute(
        "CREATE TABLE medallion_audit.jobs (job_id VARCHAR PRIMARY KEY,"
        "command_name VARCHAR,"
        "scope_ref VARCHAR,config_hash VARCHAR)"
    )
    gold.execute(
        "CREATE TABLE medallion_audit.job_events (job_id VARCHAR,event_index INTEGER,"
        "state VARCHAR,PRIMARY KEY(job_id,event_index))"
    )
    gold.execute(
        "CREATE TABLE medallion_audit.dataset_contracts (dataset_name VARCHAR,"
        "contract_version VARCHAR,fingerprint VARCHAR,contract_json VARCHAR)"
    )
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    group = digest([ASSESSMENT, versions])
    contract = {
        "name": "gold.quote_price_builds",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_gold_quote_features",
    }
    gold.execute(
        "INSERT INTO medallion_audit.dataset_contracts VALUES (?,?,?,?)",
        [contract["name"], "1", digest(contract), canonical(contract)],
    )
    gold.execute(
        "INSERT INTO gold.quote_price_definitions VALUES (?,?,?,?,?)",
        [
            FEATURE_VERSION,
            DEFINITION_FINGERPRINT,
            canonical(DEFINITION),
            datetime.now(UTC),
            "job1",
        ],
    )
    state = {"current": candidate(), "calls": 0}

    def insert(value, *, links=(), job="job1", job_state="SUCCEEDED", group_id=group):
        gold.execute(
            "INSERT INTO gold.quote_price_builds VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                value.build_id,
                group_id,
                value.source_assessment_revision_id,
                STORE_VERSION,
                FEATURE_VERSION,
                DEFINITION_FINGERPRINT,
                value.status,
                value.reason_code,
                value.source_evidence_fingerprint,
                canonical(asdict(value)),
                value.event_ts,
                value.last_trade_time,
                None,
                None,
                None,
                canonical(links),
                datetime.now(UTC),
                job,
            ],
        )
        gold.execute(
            "INSERT INTO gold.quote_price_build_attempts VALUES (?,?,?)",
            [job, value.build_id, datetime.now(UTC)],
        )
        gold.execute(
            "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
            [job, COMMAND, "sha256:" + group_id, digest(versions)],
        )
        gold.execute("INSERT INTO medallion_audit.job_events VALUES (?,1,?)", [job, job_state])

    insert(state["current"])

    def compute(*connections, assessment_revision_id):
        assert list(connections) == sources
        assert assessment_revision_id == ASSESSMENT
        state["calls"] += 1
        return state["current"]

    monkeypatch.setattr(reader, "build_quote_price_candidate", compute)

    def run(pin=state["current"].build_id):
        return reader.read_quote_price_build(*sources, gold, build_id=pin)

    yield sources, gold, state, run, insert, group
    for connection in [*sources, gold]:
        connection.close()


def test_verified_current_exact_values_and_false_eligibility(setup):
    _, _, state, run, _, _ = setup
    value = run()
    assert value.status == "verified_current"
    assert value.candidate == candidate()
    assert value.candidate.features[0].decimal_value == "123.45"
    assert value.candidate.event_ts is None
    assert value.candidate.published_at is None
    assert not value.publication_asserted
    assert not value.historical_validity_asserted
    assert not value.decision_eligibility_asserted
    assert value.successful_attempt_job_ids == ("job1",)
    assert run() == value
    assert state["calls"] == 2


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("UPDATE gold.quote_price_schema_versions SET version=2", "UNSUPPORTED_GOLD_SCHEMA"),
        ("DELETE FROM medallion_audit.dataset_contracts", "GOLD_CONTRACT_NOT_VERIFIED"),
        (
            "UPDATE gold.quote_price_builds SET store_version='bad'",
            "UNSUPPORTED_GOLD_BUILD_VERSION",
        ),
        (
            "UPDATE gold.quote_price_builds SET source_assessment_revision_id=repeat('e',64)",
            "GOLD_INPUT_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE gold.quote_price_definitions SET definition_json='[]'",
            "GOLD_DEFINITION_NOT_VERIFIED",
        ),
        (
            "UPDATE gold.quote_price_definitions SET definition_json=repeat('x',32769)",
            "GOLD_DEFINITION_NOT_VERIFIED",
        ),
        (
            "UPDATE gold.quote_price_definitions SET first_job_id='missing'",
            "GOLD_DEFINITION_ORIGIN_MISSING",
        ),
        ("UPDATE medallion_audit.jobs SET config_hash='bad'", "GOLD_DEFINITION_AUDIT_NOT_VERIFIED"),
        (
            "UPDATE medallion_audit.job_events SET state='RUNNING'",
            "GOLD_DEFINITION_AUDIT_NOT_VERIFIED",
        ),
        (
            "UPDATE gold.quote_price_builds SET first_job_id='missing'",
            "GOLD_ATTEMPT_LINEAGE_MISSING",
        ),
        (
            "UPDATE gold.quote_price_builds SET published_at=now()",
            "UNSUPPORTED_GOLD_TEMPORAL_CLAIMS",
        ),
        (
            "UPDATE gold.quote_price_builds SET effective_from=now()",
            "UNSUPPORTED_GOLD_TEMPORAL_CLAIMS",
        ),
        ("UPDATE gold.quote_price_builds SET status='blocked'", "GOLD_RESULT_IDENTITY_MISMATCH"),
        ("UPDATE gold.quote_price_builds SET result_json='{}'", "MALFORMED_GOLD_RESULT"),
        ("UPDATE gold.quote_price_builds SET result_json='not-json'", "MALFORMED_GOLD_RESULT"),
        ("UPDATE gold.quote_price_builds SET result_json=repeat('x',1048577)", "GOLD_RESULT_LIMIT"),
        ("UPDATE gold.quote_price_builds SET event_ts=now()", "GOLD_EVENT_TIME_MISMATCH"),
        ("UPDATE gold.quote_price_builds SET supersedes_json='null'", "INVALID_GOLD_HISTORY"),
        (
            "UPDATE gold.quote_price_builds SET supersedes_json='[true]'",
            "GOLD_INVALID_SUPERSESSION_LINK",
        ),
    ],
)
def test_tampering_blocks_before_source(setup, sql, reason):
    _, gold, state, run, _, _ = setup
    gold.execute(sql)
    evidence = run()
    assert evidence.status == "blocked"
    assert evidence.reason_code == reason
    assert evidence.candidate is None
    assert state["calls"] == 0


def test_failed_unsupported_blocked_successor_invalidates_old_pin(setup):
    _, gold, state, run, insert, _ = setup
    old = candidate()
    blocked = candidate("blocked")
    insert(blocked, links=(old.build_id,), job="job2", job_state="FAILED")
    gold.execute(
        "UPDATE gold.quote_price_builds SET store_version='unsupported' WHERE build_id=?",
        [blocked.build_id],
    )
    result = run()
    assert result.reason_code == "GOLD_ASSESSMENT_SUPERSEDED"
    assert result.active_build_ids == (blocked.build_id,)
    assert state["calls"] == 0


def test_two_heads_no_latest_fallback(setup):
    _, _, state, run, insert, _ = setup
    insert(candidate("blocked"), job="job2")
    assert run().reason_code == "GOLD_AMBIGUOUS_ACTIVE_ASSESSMENTS"
    assert state["calls"] == 0


@pytest.mark.parametrize("kind", ["cycle", "dangling", "duplicate"])
def test_invalid_graph(setup, kind):
    _, gold, _, run, _, _ = setup
    pin = candidate().build_id
    links = ["f" * 64] if kind == "dangling" else [pin, pin] if kind == "duplicate" else [pin]
    gold.execute("UPDATE gold.quote_price_builds SET supersedes_json=?", [canonical(links)])
    expected = {
        "cycle": "GOLD_SUPERSESSION_CYCLE",
        "dangling": "GOLD_DANGLING_SUPERSESSION_LINK",
        "duplicate": "GOLD_DUPLICATE_SUPERSESSION_LINK",
    }
    assert run().reason_code == expected[kind]


def test_stored_blocked_build_can_be_verified_without_becoming_eligible(setup):
    _, _, state, run, insert, _ = setup
    old = candidate()
    blocked = candidate("blocked")
    insert(blocked, links=(old.build_id,), job="job2")
    state["current"] = blocked
    result = run(blocked.build_id)
    assert result.status == "verified_current"
    assert result.candidate.status == "blocked"
    assert result.candidate.features == ()
    assert not result.decision_eligibility_asserted


def test_current_source_drift_blocks_without_rewriting_gold(setup):
    _, gold, state, run, _, _ = setup
    before = gold.execute("SELECT * FROM gold.quote_price_builds").fetchall()
    state["current"] = candidate("blocked")
    assert run().reason_code == "CURRENT_GOLD_SOURCE_EVIDENCE_CHANGED"
    assert gold.execute("SELECT * FROM gold.quote_price_builds").fetchall() == before


def test_pending_linked_retry_blocks_even_with_prior_success(setup):
    _, gold, _, run, _, group = setup
    gold.execute(
        "INSERT INTO gold.quote_price_build_attempts VALUES (?,?,?)",
        ["job2", candidate().build_id, datetime.now(UTC)],
    )
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    gold.execute(
        "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
        ["job2", COMMAND, "sha256:" + group, digest(versions)],
    )
    gold.execute("INSERT INTO medallion_audit.job_events VALUES ('job2',1,'RUNNING')")
    assert run().reason_code == "GOLD_ATTEMPT_NOT_TERMINAL"
    gold.execute("INSERT INTO medallion_audit.job_events VALUES ('job2',2,'FAILED')")
    assert run().status == "verified_current"


def test_shared_definition_origin_uses_its_own_input_scope(setup):
    _, gold, _, run, insert, _ = setup
    origin = replace(candidate(), source_assessment_revision_id="e" * 64, build_id="")
    origin = replace(origin, build_id=digest(asdict(origin)))
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    other_group = digest([origin.source_assessment_revision_id, versions])
    insert(origin, job="origin", group_id=other_group)
    gold.execute("UPDATE gold.quote_price_definitions SET first_job_id='origin'")
    assert run().status == "verified_current"


@pytest.mark.parametrize("zone", ["UTC", "Asia/Kolkata"])
def test_timestamp_instant_comparison_is_session_timezone_independent(setup, zone):
    _, gold, state, run, insert, _ = setup
    old = candidate()
    timed = replace(
        old,
        build_id="",
        event_ts="2026-01-01T00:00:00+00:00",
        last_trade_time="2025-12-31T23:59:59+00:00",
    )
    timed = replace(timed, build_id=digest(asdict(timed)))
    insert(timed, links=(old.build_id,), job="job2")
    state["current"] = timed
    gold.execute(f"SET TimeZone='{zone}'")
    evidence = run(timed.build_id)
    assert evidence.status == "verified_current"
    assert evidence.candidate.event_ts == "2026-01-01T00:00:00+00:00"
    assert evidence.candidate.last_trade_time == "2025-12-31T23:59:59+00:00"


@pytest.mark.parametrize("pin", ["", "A" * 64, "f" * 63])
def test_invalid_pin(setup, pin):
    _, _, state, run, _, _ = setup
    with pytest.raises(ValueError):
        run(pin)
    assert state["calls"] == 0


def test_limits_and_missing_pin(setup, monkeypatch):
    _, _, _, run, _, _ = setup
    assert run("f" * 64).reason_code == "GOLD_BUILD_NOT_FOUND"
    monkeypatch.setattr(reader, "MAX_ATTEMPTS", 0)
    assert run().reason_code == "GOLD_ATTEMPT_LIMIT"
    monkeypatch.setattr(reader, "MAX_ASSESSMENTS", 0)
    assert run().reason_code == "GOLD_HISTORY_LIMIT"


def test_source_exception_propagates(setup, monkeypatch):
    _, _, _, run, _, _ = setup

    def fail(*args, **kwargs):
        raise RuntimeError("source failure")

    monkeypatch.setattr(reader, "build_quote_price_candidate", fail)
    with pytest.raises(RuntimeError, match="source failure"):
        run()


def test_gold_cannot_alias_source_connection(setup):
    sources, gold, _, _, _, _ = setup
    with pytest.raises(ValueError, match="SEPARATE_GOLD_DATABASE_REQUIRED"):
        reader.read_quote_price_build(gold, *sources[1:], gold, build_id=candidate().build_id)


def test_session_timezone_does_not_change_evidence_identity(setup):
    _, gold, state, run, insert, _ = setup
    old = candidate()
    timed = replace(old, build_id="", event_ts="2026-01-01T00:00:00+00:00")
    timed = replace(timed, build_id=digest(asdict(timed)))
    insert(timed, links=(old.build_id,), job="job2")
    state["current"] = timed
    gold.execute("SET TimeZone='UTC'")
    first = run(timed.build_id)
    gold.execute("SET TimeZone='Asia/Kolkata'")
    assert run(timed.build_id) == first


def test_actual_read_only_gold_file_named_gold_is_unchanged(setup, tmp_path):
    sources, gold, _, _, _, _ = setup
    path = tmp_path / "gold.duckdb"
    escaped = str(path).replace("'", "''")
    gold.execute(f"ATTACH '{escaped}' AS export_target")
    gold.execute("COPY FROM DATABASE memory TO export_target")
    gold.execute("DETACH export_target")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    read_only = duckdb.connect(str(path), read_only=True)
    try:
        value = reader.read_quote_price_build(*sources, read_only, build_id=candidate().build_id)
        assert value.status == "verified_current"
        with pytest.raises(duckdb.InvalidInputException):
            read_only.execute("CREATE TABLE forbidden (id INTEGER)")
    finally:
        read_only.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_quoted_catalog_names_are_escaped(setup, tmp_path):
    sources, gold, _, _, _, _ = setup
    path = tmp_path / "gold.fixture'quoted.duckdb"
    escaped = str(path).replace("'", "''")
    alias = '"go""ld"'
    gold.execute(f"ATTACH '{escaped}' AS {alias}")
    gold.execute(f"COPY FROM DATABASE memory TO {alias}")
    gold.execute(f"USE {alias}")
    evidence = reader.read_quote_price_build(*sources, gold, build_id=candidate().build_id)
    assert evidence.status == "verified_current"


def test_missing_definition_and_oversized_history_block(setup):
    _, gold, state, run, _, _ = setup
    gold.execute("UPDATE gold.quote_price_builds SET supersedes_json=repeat('x',100001)")
    assert run().reason_code == "INVALID_GOLD_HISTORY"
    gold.execute("UPDATE gold.quote_price_builds SET supersedes_json='[]'")
    gold.execute("DELETE FROM gold.quote_price_definitions")
    assert run().reason_code == "GOLD_DEFINITION_NOT_VERIFIED"
    assert state["calls"] == 0


def test_active_build_needs_success_without_falling_back_to_old_build(setup):
    _, gold, state, run, insert, group = setup
    old = candidate()
    blocked = candidate("blocked")
    insert(blocked, links=(old.build_id,), job="job2", job_state="FAILED")
    state["current"] = blocked
    assert run(blocked.build_id).reason_code == "GOLD_NO_SUCCESSFUL_ATTEMPT"
    assert run().reason_code == "GOLD_ASSESSMENT_SUPERSEDED"
    assert state["calls"] == 0
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    gold.execute(
        "INSERT INTO gold.quote_price_build_attempts VALUES (?,?,?)",
        ["job3", blocked.build_id, datetime.now(UTC)],
    )
    gold.execute(
        "INSERT INTO medallion_audit.jobs VALUES (?,?,?,?)",
        ["job3", COMMAND, "sha256:" + group, digest(versions)],
    )
    gold.execute("INSERT INTO medallion_audit.job_events VALUES ('job3',1,'SUCCEEDED')")
    value = run(blocked.build_id)
    assert value.status == "verified_current"
    assert value.successful_attempt_job_ids == ("job3",)
    assert value.candidate.status == "blocked"


@pytest.mark.parametrize("kind", ["duplicate_key", "nonfinite"])
def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(setup, kind):
    _, gold, state, run, _, _ = setup
    original = canonical(asdict(candidate()))
    if kind == "duplicate_key":
        changed = original.replace('"build_id":', '"build_id":"ignored","build_id":', 1)
    else:
        changed = original.replace('"provider_token":null', '"provider_token":NaN')
    gold.execute("UPDATE gold.quote_price_builds SET result_json=?", [changed])
    assert run().reason_code == "MALFORMED_GOLD_RESULT"
    assert state["calls"] == 0
