"""Synthetic SQL scope fixtures on real DuckDB, NOT native source/audit E2E."""

import json
from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform.research_iv_record import build_id, canonical, input_id, sha
from nse_quant.data_platform.research_iv_store import (
    COMMAND,
    FEATURE_VERSION,
    IvArchiveReviewRequired,
    _name,
    _scope,
)

DEFINITION = "a" * 64
TERMS = canonical(
    dict(
        strike="100",
        annual_rate="0.05",
        annual_dividend_yield="0.02",
        assumed_years_to_expiry="1",
        option_type="CE",
    )
)
TERMS_PIN = sha(canonical(["research-european-bsm-iv@1", json.loads(TERMS)]).encode())
GROUP = input_id("b" * 64, "c" * 64, TERMS_PIN, DEFINITION)


@pytest.fixture
def sql_fixture(tmp_path):
    with duckdb.connect(str(tmp_path / "gold.duckdb")) as conn:
        conn.execute('CREATE SCHEMA "gold"')
        conn.execute('CREATE SCHEMA "medallion_audit"')
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', 'research_iv_builds')} ("
            "build_id VARCHAR,input_id VARCHAR,ordinal INTEGER,feature_version VARCHAR,"
            "option_build_id VARCHAR,spot_build_id VARCHAR,terms_pin VARCHAR,"
            "definition_hash VARCHAR,terms_json VARCHAR,result_json VARCHAR,"
            "prior_ids_json VARCHAR,first_job_id VARCHAR,recorded_at TIMESTAMPTZ,"
            "event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', 'research_iv_attempts')} "
            "(job_id VARCHAR,input_id VARCHAR,build_id VARCHAR)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'medallion_audit', 'jobs')} "
            "(job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,"
            "config_hash VARCHAR,"
            "created_at TIMESTAMPTZ,actor_id VARCHAR,code_revision VARCHAR,"
            "scope_ref VARCHAR)"
        )
        events = _name(conn, "medallion_audit", "job_events")
        conn.execute(
            f"CREATE TABLE {events} "
            "(job_id VARCHAR,event_index INTEGER,state VARCHAR,recorded_at TIMESTAMPTZ,"
            "reason_code VARCHAR)"
        )
        yield conn


def insert(conn, ordinal=1, prior=(), status="review_required", job="j1"):
    value = dict(
        version="native-gold-research-iv-candidate@1",
        option_build_id="b" * 64,
        spot_build_id="c" * 64,
        scenario_terms_sha256=TERMS_PIN,
        status=status,
        canonical_contract_id=None,
        scenario_terms_authoritative=False,
        option_underlying_identity_binding_verified=False,
        availability_evidence_verified=False,
        historical_validity_asserted=False,
        publication_asserted=False,
        decision_eligibility_asserted=False,
        atomic_cross_database_snapshot_asserted=False,
    )
    raw = canonical(value)
    key = build_id(GROUP, raw)
    clock = datetime.now(UTC)
    conn.execute(
        f"INSERT INTO {_name(conn, 'gold', 'research_iv_builds')} "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            key,
            GROUP,
            ordinal,
            FEATURE_VERSION,
            "b" * 64,
            "c" * 64,
            TERMS_PIN,
            DEFINITION,
            TERMS,
            raw,
            canonical(prior),
            job,
            clock,
            None,
            None,
        ],
    )
    conn.execute(
        f"INSERT INTO {_name(conn, 'gold', 'research_iv_attempts')} VALUES (?,?,?)",
        [job, GROUP, key],
    )
    conn.execute(
        f"INSERT INTO {_name(conn, 'medallion_audit', 'jobs')} VALUES (?,?,?,?,?,?,?,?)",
        [job, None, COMMAND, DEFINITION, clock, "synthetic", "synthetic", GROUP],
    )
    for index, state in enumerate(("PLANNED", "RUNNING", "SUCCEEDED"), 1):
        events = _name(conn, "medallion_audit", "job_events")
        conn.execute(f"INSERT INTO {events} VALUES (?,?,?,?,?)", [job, index, state, clock, None])
    return key


def test_empty_scope_and_quoted_catalog_equal_schema(sql_fixture):
    rows, fingerprint = _scope(sql_fixture, GROUP, DEFINITION)
    assert rows == [] and len(fingerprint) == 64


def test_positive_synthetic_scope_clock_normalization(sql_fixture):
    insert(sql_fixture)
    before = _scope(sql_fixture, GROUP, DEFINITION)[1]
    sql_fixture.execute("SET TimeZone='Asia/Kolkata'")
    assert _scope(sql_fixture, GROUP, DEFINITION)[1] == before


def test_negative_new_distinct_record_remains_in_history(sql_fixture):
    old = insert(sql_fixture, status="research_iv_candidate")
    new = insert(sql_fixture, 2, (old,), job="j2")
    rows, _ = _scope(sql_fixture, GROUP, DEFINITION)
    assert [row[0] for row in rows] == [old, new]


def test_failed_origin_not_repaired_by_success_state(sql_fixture):
    insert(sql_fixture)
    events = _name(sql_fixture, "medallion_audit", "job_events")
    sql_fixture.execute(f"UPDATE {events} SET state='FAILED' WHERE event_index=2")
    with pytest.raises(IvArchiveReviewRequired, match="AUDIT_OBLIGATION"):
        _scope(sql_fixture, GROUP, DEFINITION)


def test_missing_origin_attempt_blocks(sql_fixture):
    insert(sql_fixture)
    sql_fixture.execute(f"DELETE FROM {_name(sql_fixture, 'gold', 'research_iv_attempts')}")
    with pytest.raises(IvArchiveReviewRequired):
        _scope(sql_fixture, GROUP, DEFINITION)


def test_missing_prior_link_never_selects_latest_success(sql_fixture):
    insert(sql_fixture, status="research_iv_candidate")
    insert(sql_fixture, 2, job="j2")
    with pytest.raises(ValueError, match="ALL_PRIOR"):
        _scope(sql_fixture, GROUP, DEFINITION)


def test_incomplete_unlinked_scope_job_blocks(sql_fixture):
    insert(sql_fixture)
    clock = datetime.now(UTC)
    sql_fixture.execute(
        f"INSERT INTO {_name(sql_fixture, 'medallion_audit', 'jobs')} VALUES (?,?,?,?,?,?,?,?)",
        ["j2", None, COMMAND, DEFINITION, clock, "synthetic", "synthetic", GROUP],
    )
    with pytest.raises(IvArchiveReviewRequired, match="AUDIT_OBLIGATION"):
        _scope(sql_fixture, GROUP, DEFINITION)


def test_temporal_claim_injection_blocks(sql_fixture):
    insert(sql_fixture)
    sql_fixture.execute(
        f"UPDATE {_name(sql_fixture, 'gold', 'research_iv_builds')} SET published_at=now()"
    )
    with pytest.raises(IvArchiveReviewRequired, match="TEMPORAL"):
        _scope(sql_fixture, GROUP, DEFINITION)
