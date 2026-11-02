"""Actual audit/store/model/Gold SQL integration with existing source-kernel substitute.

NOT full native acquisition-to-analytics E2E. No candidate result is fabricated here.
"""

import duckdb
import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_option_boundary import scenario as scenario

from nse_quant.data_platform import research_iv_store as store
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.research_option_model import ScenarioTerms, scenario_terms_sha256


@pytest.fixture
def archive_case(scenario, setup, tmp_path):
    _, current, option, spot, _, _ = scenario
    sources, source_gold, _, _, _, _ = setup
    target = duckdb.connect(str(tmp_path / "research_iv.duckdb"))
    terms = ScenarioTerms("1000", "0.05", "0.02", "1", "CE")

    def persist(override=None, initialize=True):
        selected = terms if override is None else override
        return store.persist_research_iv_build(
            *sources,
            source_gold,
            target,
            option_build_id=option.build_id,
            spot_build_id=spot.build_id,
            terms=selected,
            expected_scenario_terms_sha256=scenario_terms_sha256(selected),
            actor_id="test",
            code_revision="synthetic",
            initialize=initialize,
        )

    yield target, persist, current, option, terms
    target.close()


def count(conn, schema, table):
    row = conn.execute(f"SELECT count(*) FROM {store._name(conn, schema, table)}").fetchone()
    assert row is not None
    return row[0]


def test_real_domain_retry_and_archived_head_preserve_origin(archive_case):
    conn, persist, _, _, _ = archive_case
    first = persist()
    builds = store._name(conn, "gold", "research_iv_builds")
    origin_sql = f"SELECT first_job_id,recorded_at,prior_ids_json FROM {builds}"
    origin = conn.execute(origin_sql).fetchone()
    second = persist(initialize=False)
    assert second["build_id"] == first["build_id"]
    assert second["inserted"] is False
    assert count(conn, "gold", "research_iv_builds") == 1
    assert count(conn, "gold", "research_iv_attempts") == 2
    assert conn.execute(origin_sql).fetchone() == origin
    value = store.read_research_iv_archive(conn, build_id_pin=first["build_id"])
    assert value.archived_recording_verified
    assert value.archived_pin_is_head
    assert not value.current_source_checked
    assert not value.publication_asserted
    assert not value.decision_eligibility_asserted
    assert value.canonical_contract_id is None


def test_review_required_successor_invalidates_old_and_retry_does_not_revive(archive_case):
    from dataclasses import replace

    conn, persist, current, option, _ = archive_case
    first = persist()
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    blocked = persist()
    assert blocked["status"] == "review_required"
    old = store.read_research_iv_archive(conn, build_id_pin=first["build_id"])
    assert not old.archived_pin_is_head
    assert old.retained_head_build_id == blocked["build_id"]
    current[option.source_assessment_revision_id] = option
    retry = persist()
    assert retry["build_id"] == first["build_id"]
    archived = store.read_research_iv_archive(conn, build_id_pin=first["build_id"])
    assert not archived.archived_pin_is_head


def test_final_audit_failure_is_not_repaired(archive_case, monkeypatch):
    conn, persist, _, _, _ = archive_case
    real = AuditLedger.transition

    def fail(self, job_id, state, reason_code=None):
        if state == JobState.SUCCEEDED:
            raise RuntimeError("SYNTHETIC_FINAL_AUDIT_FAILURE")
        return real(self, job_id, state, reason_code)

    monkeypatch.setattr(AuditLedger, "transition", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_FINAL_AUDIT_FAILURE"):
        persist()
    assert count(conn, "gold", "research_iv_builds") == 1
    monkeypatch.setattr(AuditLedger, "transition", real)
    with pytest.raises(store.IvArchiveReviewRequired, match="AUDIT_OBLIGATION"):
        persist()


def test_contract_definition_build_attempt_roll_back_together(archive_case, monkeypatch):
    conn, persist, _, _, _ = archive_case
    real = AuditLedger.register_contract

    def fail_after_contract(self, contract):
        real(self, contract)
        raise RuntimeError("SYNTHETIC_DOMAIN_FAILURE")

    monkeypatch.setattr(AuditLedger, "register_contract", fail_after_contract)
    with pytest.raises(RuntimeError, match="SYNTHETIC_DOMAIN_FAILURE"):
        persist()
    for table in ("research_iv_definitions", "research_iv_builds", "research_iv_attempts"):
        assert count(conn, "gold", table) == 0
    assert count(conn, "medallion_audit", "dataset_contracts") == 0


def test_definition_origin_checked_in_its_own_input_scope(archive_case):
    conn, persist, _, _, terms = archive_case
    first = persist()
    alternate = ScenarioTerms(
        "1050",
        terms.annual_rate,
        terms.annual_dividend_yield,
        terms.assumed_years_to_expiry,
        terms.option_type,
    )
    second = persist(alternate)
    assert first["input_id"] != second["input_id"]
    archived = store.read_research_iv_archive(conn, build_id_pin=second["build_id"])
    assert archived.archived_pin_is_head


def test_archive_readonly_and_timezone(archive_case, tmp_path):
    conn, persist, _, _, _ = archive_case
    first = persist()
    before = store.read_research_iv_archive(conn, build_id_pin=first["build_id"])
    conn.execute("SET TimeZone='Asia/Kolkata'")
    assert store.read_research_iv_archive(conn, build_id_pin=first["build_id"]) == before
    conn.close()
    with duckdb.connect(str(tmp_path / "research_iv.duckdb"), read_only=True) as read_only:
        assert store.read_research_iv_archive(read_only, build_id_pin=first["build_id"]) == before


def test_source_target_cursor_alias_refused_before_initialization(archive_case):
    conn, _, _, option, terms = archive_case
    cursor = conn.cursor()
    assert cursor is not conn
    current = conn.execute("SELECT current_database()").fetchone()
    assert current is not None
    alias = '"' + current[0].replace('"', '""') + '"'
    cursor.execute(f"USE {alias}")
    try:
        with pytest.raises(ValueError, match="SEPARATE_RESEARCH_IV_OUTPUT"):
            store.persist_research_iv_build(
                cursor,
                cursor,
                cursor,
                cursor,
                cursor,
                conn,
                option_build_id=option.build_id,
                spot_build_id="f" * 64,
                terms=terms,
                expected_scenario_terms_sha256=scenario_terms_sha256(terms),
                actor_id="test",
                code_revision="synthetic",
                initialize=True,
            )
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        cursor.close()
