"""Tests for read-only Silver schema inspector."""

from __future__ import annotations

import duckdb
import pytest

from scripts.migration.inspect_option_stream_silver_schema import main


def _create_tables(db):
    conn = duckdb.connect(str(db))
    # DuckDB derives the attached catalog name from the database filename.
    # For silver.duckdb, the catalog is "silver"; qualify schema explicitly.
    conn.execute("CREATE SCHEMA silver.silver")
    conn.execute("CREATE TABLE silver.silver.option_stream_revisions (revision_id VARCHAR)")
    conn.execute("CREATE TABLE silver.silver.option_stream_observations (revision_id VARCHAR)")
    conn.close()


def test_inspector_requires_existing_tables(tmp_path):
    db = tmp_path / "silver.duckdb"
    _create_tables(db)
    assert main(argv=["--silver-db", str(db), "--limit", "1"]) == 0


def test_inspector_fails_on_missing_table(tmp_path):
    db = tmp_path / "silver.duckdb"
    conn = duckdb.connect(str(db))
    conn.execute("CREATE SCHEMA silver.silver")
    conn.close()
    with pytest.raises(SystemExit, match="MISSING_SILVER_TABLE"):
        main(argv=["--silver-db", str(db)])
