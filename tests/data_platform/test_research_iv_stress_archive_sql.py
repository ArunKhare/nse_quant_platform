"""Actual DuckDB synthetic schema checks, not an audit replica or native integration."""

import duckdb
import pytest

from nse_quant.data_platform import research_iv_stress_archive as store


@pytest.fixture
def synthetic(tmp_path):
    with duckdb.connect(str(tmp_path / "synthetic-archive.duckdb")) as conn:
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        catalog = '"' + str(row[0]).replace('"', '""') + '"'
        for schema in ("gold", "medallion_audit"):
            conn.execute(f'CREATE SCHEMA {catalog}."{schema}"')
        definitions = {
            "schema_versions": "version INTEGER,applied_at TIMESTAMPTZ",
            "dataset_contracts": "dataset_name VARCHAR,contract_version VARCHAR,"
            "fingerprint VARCHAR,"
            "contract_json VARCHAR,registered_at TIMESTAMPTZ",
            "jobs": "job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,actor_id VARCHAR,"
            "scope_ref VARCHAR,code_revision VARCHAR,config_hash VARCHAR,"
            "created_at TIMESTAMPTZ",
            "job_events": "job_id VARCHAR,event_index INTEGER,state VARCHAR,"
            "recorded_at TIMESTAMPTZ,"
            "reason_code VARCHAR",
        }
        for name, columns in definitions.items():
            conn.execute(f"CREATE TABLE {store._name(conn, 'medallion_audit', name)} ({columns})")
        conn.execute(
            f"INSERT INTO {store._name(conn, 'medallion_audit', 'schema_versions')} "
            "VALUES (1,current_timestamp)"
        )
        conn.execute(
            f"CREATE TABLE {store._name(conn, 'gold', store.TABLE)} "
            "(build_id VARCHAR,scope_id VARCHAR,record_json VARCHAR,"
            "feature_version VARCHAR,"
            "first_job_id VARCHAR,recorded_at TIMESTAMPTZ,event_ts TIMESTAMPTZ,"
            "published_at TIMESTAMPTZ)"
        )
        yield conn


def test_empty_whole_store_stable_but_not_a_record(synthetic):
    assert store._snapshot(synthetic) == store._snapshot(synthetic)
    with pytest.raises(store.IvStressArchiveReviewRequired, match="EXACT_RECORD_NOT_FOUND"):
        store.read_research_iv_spot_stress_archive(synthetic, build_id_pin="a" * 64)


def test_orphan_events_invalidate_empty_domain(synthetic):
    name = store._name(synthetic, "medallion_audit", "job_events")
    synthetic.execute(f"INSERT INTO {name} VALUES ('orphan',1,'FAILED',current_timestamp,NULL)")
    with pytest.raises(store.IvStressArchiveReviewRequired, match="ORPHAN_EVENTS"):
        store._snapshot(synthetic)


def test_other_scope_pending_job_not_filtered_away(synthetic):
    name = store._name(synthetic, "medallion_audit", "jobs")
    synthetic.execute(
        f"INSERT INTO {name} VALUES "
        "('pending',NULL,?,'synthetic','other','synthetic',?,current_timestamp)",
        [store.COMMAND, store.record.sha(store.record.canonical(store.record.DEFINITION).encode())],
    )
    with pytest.raises(store.IvStressArchiveReviewRequired, match="UNLINKED_JOB"):
        store._snapshot(synthetic)


def test_event_budget_never_accepts_prefix(synthetic):
    name = store._name(synthetic, "medallion_audit", "job_events")
    synthetic.executemany(
        f"INSERT INTO {name} VALUES ('orphan',?,'FAILED',current_timestamp,NULL)",
        [(i,) for i in range(65)],
    )
    with pytest.raises(store.IvStressArchiveReviewRequired, match="PROFILE_LIMIT"):
        store._snapshot(synthetic)
