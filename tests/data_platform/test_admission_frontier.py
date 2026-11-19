"""Real DuckDB scanner tests on synthetic SQL fixtures, not native lifecycle E2E."""

from datetime import UTC, datetime

import duckdb
import pytest

from nse_quant.data_platform import admission_frontier as frontier


def open_catalog(path, catalog, *, read_only=False):
    connection = duckdb.connect(":memory:")
    escaped_path = str(path).replace("'", "''")
    mode = " (READ_ONLY)" if read_only else ""
    quoted_catalog = frontier._quote(catalog)

    try:
        connection.execute(f"ATTACH '{escaped_path}' AS {quoted_catalog}{mode}")
        connection.execute(f"USE {quoted_catalog}")
    except BaseException:
        connection.close()
        raise

    return connection


@pytest.fixture(params=["decision_inputs", "odd'catalog\"name"])
def database(tmp_path, request):
    connection = open_catalog(
        tmp_path / "capture.duckdb",
        request.param,
    )
    catalog = connection.execute("SELECT current_database()").fetchone()[0]
    for schema, table in frontier.TABLES:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {frontier._quote(schema)}")
        definitions = []
        for column in frontier.TABLES[(schema, table)]:
            kind = "VARCHAR"
            if column in {"version", "event_index"}:
                kind = "INTEGER"
            elif column == "receipt_byte_count":
                kind = "BIGINT"
            elif column in {"research_analysis_permitted", "decision_eligibility_asserted"}:
                kind = "BOOLEAN"
            elif column == "receipt_bytes":
                kind = "BLOB"
            elif column.endswith("_at") or column == "request_knowledge_cutoff":
                kind = "TIMESTAMPTZ"
            definitions.append(frontier._quote(column) + " " + kind)
        name = ".".join(map(frontier._quote, (catalog, schema, table)))
        connection.execute(f"CREATE TABLE {name} ({','.join(definitions)})")
    yield connection
    connection.close()


def qualified(connection, schema, table):
    catalog = connection.execute("SELECT current_database()").fetchone()[0]
    return ".".join(map(frontier._quote, (catalog, schema, table)))


def test_stable_complete_fingerprint_is_not_provenance(database):
    first = frontier.observe_admission_frontier(database)
    second = frontier.observe_admission_frontier(database)
    assert first == second
    assert len(first.table_row_counts) == 9
    assert first.hashed_blob_bytes == 0
    assert not first.provenance_verified
    assert not first.authenticity_asserted
    assert not first.decision_eligibility_asserted


@pytest.mark.parametrize(("schema", "table"), sorted(frontier.TABLES))
def test_each_table_contributes_even_unlinked_or_failed_evidence(database, schema, table):
    first = frontier.observe_admission_frontier(database)
    name = qualified(database, schema, table)
    database.execute(f"INSERT INTO {name} DEFAULT VALUES")
    second = frontier.observe_admission_frontier(database)
    assert first.fingerprint != second.fingerprint


def test_exact_blob_bytes_change_frontier_without_returning_payload(database):
    name = qualified(database, "decision_inputs", "admission_receipts")
    database.execute(f"INSERT INTO {name} (receipt_bytes) VALUES (?)", [b"private-a"])
    first = frontier.observe_admission_frontier(database)
    database.execute(f"UPDATE {name} SET receipt_bytes=?", [b"private-b"])
    second = frontier.observe_admission_frontier(database)
    assert first.fingerprint != second.fingerprint
    assert first.hashed_blob_bytes == len(b"private-a")
    assert "private-a" not in repr(first)


def test_timezone_equivalent_fingerprint(database):
    name = qualified(database, "medallion_audit", "jobs")
    database.execute(f"INSERT INTO {name} (created_at) VALUES (?)", [datetime.now(UTC)])
    first = frontier.observe_admission_frontier(database)
    database.execute("SET TimeZone='Asia/Kolkata'")
    assert frontier.observe_admission_frontier(database).fingerprint == first.fingerprint


def test_row_order_independent_but_multiplicity_preserved(database):
    name = qualified(database, "medallion_audit", "jobs")
    database.execute(f"INSERT INTO {name} (job_id) VALUES ('a'),('b')")
    first = frontier.observe_admission_frontier(database)
    database.execute(f"DELETE FROM {name}")
    database.execute(f"INSERT INTO {name} (job_id) VALUES ('b'),('a')")
    assert frontier.observe_admission_frontier(database).fingerprint == first.fingerprint
    database.execute(f"INSERT INTO {name} (job_id) VALUES ('a')")
    assert frontier.observe_admission_frontier(database).fingerprint != first.fingerprint


@pytest.mark.parametrize("kind", ["row", "text", "blob", "total_blob", "document"])
def test_limits_never_return_partial_frontier(database, monkeypatch, kind):
    name = qualified(database, "decision_inputs", "admission_receipts")
    database.execute(f"INSERT INTO {name} (receipt_bytes,status) VALUES (?,?)", [b"abc", "abc"])
    if kind == "row":
        monkeypatch.setitem(frontier.LIMITS, ("decision_inputs", "admission_receipts"), 0)
    else:
        constant = {
            "text": "MAX_TEXT_CELL",
            "blob": "MAX_BLOB_CELL",
            "total_blob": "MAX_BLOB_TOTAL",
            "document": "MAX_DOCUMENT_BYTES",
        }[kind]
        monkeypatch.setattr(frontier, constant, 1)
    with pytest.raises(frontier.FrontierReviewRequired):
        frontier.observe_admission_frontier(database)
    assert database.execute("SELECT 1").fetchone() == (1,)


def test_extra_table_or_column_requires_review(database):
    database.execute("CREATE TABLE unexpected(id INTEGER)")
    with pytest.raises(frontier.FrontierReviewRequired, match="INVENTORY"):
        frontier.observe_admission_frontier(database)
    database.execute("DROP TABLE unexpected")
    name = qualified(database, "decision_inputs", "admission_receipts")
    database.execute(f"ALTER TABLE {name} ADD COLUMN unexpected INTEGER")
    with pytest.raises(frontier.FrontierReviewRequired, match="COLUMN_SHAPE"):
        frontier.observe_admission_frontier(database)


def test_missing_schema_produces_review_not_global_health(tmp_path):
    with (
        duckdb.connect(str(tmp_path / "empty.duckdb")) as conn,
        pytest.raises(frontier.FrontierReviewRequired, match="INVENTORY"),
    ):
        frontier.observe_admission_frontier(conn)


def test_actual_readonly_database_observation(database):
    catalog = database.execute("SELECT current_database()").fetchone()[0]
    path = next(
        row[2] for row in database.execute("PRAGMA database_list").fetchall() if row[1] == catalog
    )
    expected = frontier.observe_admission_frontier(database)
    database.close()

    with open_catalog(path, catalog, read_only=True) as connection:
        assert frontier.observe_admission_frontier(connection) == expected


def test_quote_escapes_catalog_delimiters():
    assert frontier._quote('catalog"name') == '"catalog""name"'


def test_cli_plan_no_execution_import_or_files(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.admission_frontier_cli import main

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.admission_frontier"}:
            raise AssertionError("Plan imported execution dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert main(["--receipt-db", str(tmp_path / "absent.duckdb")]) == 0
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
