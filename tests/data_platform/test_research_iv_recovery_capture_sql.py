"""Actual DuckDB synthetic schema rejection checks; NOT native service integration."""

import duckdb
import pytest

from nse_quant.data_platform import research_iv_recovery_capture as store


@pytest.fixture
def synthetic(tmp_path):
    with duckdb.connect(str(tmp_path / "safe-schema.duckdb")) as conn:
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        catalog = '"' + str(row[0]).replace('"', '""') + '"'
        conn.execute(f'CREATE SCHEMA {catalog}."medallion_audit"')
        conn.execute(f'CREATE SCHEMA {catalog}."gold"')
        definitions = {
            "schema_versions": "version INTEGER,applied_at TIMESTAMPTZ",
            "dataset_contracts": "dataset_name VARCHAR,contract_version VARCHAR,"
            "fingerprint VARCHAR,contract_json VARCHAR,"
            "registered_at TIMESTAMPTZ",
            "jobs": "job_id VARCHAR,parent_job_id VARCHAR,command_name VARCHAR,actor_id VARCHAR,"
            "scope_ref VARCHAR,code_revision VARCHAR,config_hash VARCHAR,"
            "created_at TIMESTAMPTZ",
            "job_events": "job_id VARCHAR,event_index INTEGER,state VARCHAR,"
            "recorded_at TIMESTAMPTZ,reason_code VARCHAR",
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


def test_empty_synthetic_profile_is_stable(synthetic):
    assert store._snapshot(synthetic) == store._snapshot(synthetic)


def test_orphan_event_blocks_empty_domain(synthetic):
    name = store._name(synthetic, "medallion_audit", "job_events")
    synthetic.execute(f"INSERT INTO {name} VALUES ('missing',1,'SUCCEEDED',current_timestamp,NULL)")
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="ORPHAN_EVENTS"):
        store._snapshot(synthetic)


def test_unlinked_job_blocks_other_scope(synthetic):
    name = store._name(synthetic, "medallion_audit", "jobs")
    synthetic.execute(
        f"INSERT INTO {name} VALUES "
        "('unlinked',NULL,?, 'synthetic','other','synthetic',?,current_timestamp)",
        [store.COMMAND, store.sha(store.canonical(store.DEFINITION).encode())],
    )
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="OBLIGATION_FAILED"):
        store._snapshot(synthetic)


def test_profile_event_bound_is_not_prefix_acceptance(synthetic):
    name = store._name(synthetic, "medallion_audit", "job_events")
    synthetic.executemany(
        f"INSERT INTO {name} VALUES ('missing',?,'FAILED',current_timestamp,NULL)",
        [(i,) for i in range(65)],
    )
    with pytest.raises(store.IvRecoveryCaptureReviewRequired, match="PROFILE_LIMIT"):
        store._snapshot(synthetic)
