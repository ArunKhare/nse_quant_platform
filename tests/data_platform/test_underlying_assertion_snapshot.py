"""Actual DuckDB snapshot on synthetic SQL fixtures, NOT native provenance E2E."""

import duckdb
import pytest

from nse_quant.data_platform import underlying_assertion_reader as reader
from nse_quant.data_platform.underlying_assertion_history import AssertionReviewRequired


@pytest.fixture(params=["identity_evidence", "odd'catalog\"name"])
def registry_snapshot(tmp_path, request):
    connection = duckdb.connect(":memory:")
    path = str(tmp_path / "identity.duckdb").replace("'", "''")
    alias = reader._quote(request.param)
    connection.execute(f"ATTACH '{path}' AS {alias}")
    connection.execute(f"USE {alias}")
    for (schema, table), columns in reader.COLUMNS.items():
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {reader._quote(schema)}")
        definitions = []
        for column in columns:
            kind = "VARCHAR"
            if column in {"version", "event_index"} and table not in {"contracts", "definitions"}:
                kind = "INTEGER"
            if column == "byte_count":
                kind = "BIGINT"
            if column == "assertion_bytes":
                kind = "BLOB"
            if column.endswith("_at"):
                kind = "TIMESTAMPTZ"
            definitions.append(reader._quote(column) + " " + kind)
        name = ".".join(map(reader._quote, (request.param, schema, table)))
        connection.execute(f"CREATE TABLE {name} ({','.join(definitions)})")
    yield connection
    connection.close()


def name(conn, schema, table):
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    return ".".join(map(reader._quote, (catalog, schema, table)))


def test_all_owned_tables_observed_but_not_validated(registry_snapshot):
    result = reader.snapshot(registry_snapshot)
    assert set(result) == set(reader.COLUMNS)
    assert all(rows == [] for rows in result.values())


@pytest.mark.parametrize(
    ("column", "value"),
    [
        pytest.param(
            "prior_assertion_ids_json",
            "x" * 70001,
            id="oversized-prior-links",
        ),
        pytest.param(
            "assertion_bytes",
            b"x" * 16385,
            id="oversized-statement-blob",
        ),
        pytest.param(
            "first_job_id",
            "x" * 4097,
            id="oversized-origin-job-id",
        ),
    ],
)
def test_no_oversized_value_is_silently_replaced_by_null(registry_snapshot, column, value):
    table = name(registry_snapshot, "identity_evidence", "assertions")
    registry_snapshot.execute(f"INSERT INTO {table} ({reader._quote(column)}) VALUES (?)", [value])
    with pytest.raises(AssertionReviewRequired):
        reader.snapshot(registry_snapshot)
    assert registry_snapshot.execute("SELECT 1").fetchone() == (1,)


def test_count_and_total_bounds(registry_snapshot, monkeypatch):
    table = name(registry_snapshot, "identity_evidence", "assertions")
    registry_snapshot.execute(f"INSERT INTO {table} (assertion_bytes) VALUES (?)", [b"test"])
    monkeypatch.setitem(reader.LIMITS, ("identity_evidence", "assertions"), 0)
    with pytest.raises(AssertionReviewRequired):
        reader.snapshot(registry_snapshot)
    monkeypatch.setitem(reader.LIMITS, ("identity_evidence", "assertions"), 1001)
    monkeypatch.setattr(reader, "MAX_DOCUMENT_BYTES", 1)
    with pytest.raises(AssertionReviewRequired):
        reader.snapshot(registry_snapshot)


def test_extra_table_and_column_are_not_ignored(registry_snapshot):
    registry_snapshot.execute("CREATE TABLE unexpected(id INTEGER)")
    with pytest.raises(AssertionReviewRequired):
        reader.snapshot(registry_snapshot)
    registry_snapshot.execute("DROP TABLE unexpected")
    table = name(registry_snapshot, "identity_evidence", "assertions")
    registry_snapshot.execute(f"ALTER TABLE {table} ADD COLUMN unexpected INTEGER")
    with pytest.raises(AssertionReviewRequired):
        reader.snapshot(registry_snapshot)


def test_readonly_current_attached_catalog(registry_snapshot):
    current = registry_snapshot.execute("SELECT current_database()").fetchone()[0]
    path = next(
        row[2]
        for row in registry_snapshot.execute("PRAGMA database_list").fetchall()
        if row[1] == current
    )
    expected = reader.snapshot(registry_snapshot)
    registry_snapshot.close()
    with duckdb.connect(":memory:") as conn:
        escaped = path.replace("'", "''")
        conn.execute(f"ATTACH '{escaped}' AS {reader._quote(current)} (READ_ONLY)")
        conn.execute(f"USE {reader._quote(current)}")
        assert reader.snapshot(conn) == expected


def test_cli_no_io_default(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.underlying_assertion_inspect_cli import main

    original = builtins.__import__

    def guarded(module, *args, **kwargs):
        if module in {"duckdb", "nse_quant.data_platform.underlying_assertion_reader"}:
            raise AssertionError("Planning imported execution")
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(["--identity-db", str(tmp_path / "missing.duckdb"), "--assertion-id", "a" * 64]) == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
