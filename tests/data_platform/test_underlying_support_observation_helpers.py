"""Actual SQL/observation helpers only; NOT recording/source integration verification."""

import duckdb
import pytest

from nse_quant.data_platform import underlying_support_revalidation as service


@pytest.fixture(
    params=[
        pytest.param("identity_evidence", id="schema-collision"),
        pytest.param("odd'catalog\"name", id="quoted-catalog"),
    ]
)
def statements(tmp_path, request):
    conn = duckdb.connect(":memory:")
    path = str(tmp_path / "identity.duckdb").replace("'", "''")
    alias = '"' + request.param.replace('"', '""') + '"'
    conn.execute(f"ATTACH '{path}' AS {alias}")
    conn.execute(f"USE {alias}")
    conn.execute("CREATE SCHEMA identity_evidence")
    table = f'{alias}."identity_evidence"."assertions"'
    conn.execute(f"CREATE TABLE {table}(assertion_id VARCHAR,assertion_bytes BLOB)")
    yield conn, table
    conn.close()


def test_exact_bounded_statement_retrieval_is_not_verification(statements):
    conn, table = statements
    conn.execute(f"INSERT INTO {table} VALUES (?,?)", ["a" * 64, b"not-a-valid-statement"])
    assert service._statement_bytes(conn, "a" * 64) == b"not-a-valid-statement"
    assert service._statement_bytes(conn, "b" * 64) is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="null"),
        pytest.param(b"x" * 16385, id="oversized"),
    ],
)
def test_missing_or_oversized_bytes_never_salvaged(statements, payload):
    conn, table = statements
    conn.execute(f"INSERT INTO {table} VALUES (?,?)", ["a" * 64, payload])
    assert service._statement_bytes(conn, "a" * 64) is None


def test_duplicate_rows_are_not_first_or_last_wins(statements):
    conn, table = statements
    conn.execute(f"INSERT INTO {table} VALUES (?,?),(?,?)", ["a" * 64, b"one", "a" * 64, b"two"])
    assert service._statement_bytes(conn, "a" * 64) is None


def test_exact_pin_required_before_sql(statements):
    conn, _ = statements
    with pytest.raises(ValueError, match="EXACT"):
        service._statement_bytes(conn, "BAD")


def test_distinct_current_files_and_attached_aliases(statements, tmp_path):
    conn, _ = statements

    with duckdb.connect(str(tmp_path / "bronze.duckdb")) as other:
        service._distinct_files(conn, other)

        with pytest.raises(ValueError, match="SEPARATE"):
            service._distinct_files(conn, conn)

    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    quoted_catalog = '"' + catalog.replace('"', '""') + '"'

    # Share the existing attached catalog through a distinct handle.
    # Do not attach the same live file into another database instance.
    with conn.cursor() as alias:
        assert alias is not conn
        alias.execute(f"USE {quoted_catalog}")

        with pytest.raises(ValueError, match="SEPARATE"):
            service._distinct_files(conn, alias)

    assert conn.execute("SELECT 1").fetchone() == (1,)


def test_inmemory_input_not_silently_accepted(statements):
    conn, _ = statements
    with duckdb.connect(":memory:") as memory, pytest.raises(ValueError, match="FILE_BACKED"):
        service._distinct_files(conn, memory)


@pytest.mark.parametrize("left,right", [(False, 0), (True, 1), (None, False)])
def test_comparison_does_not_coerce_authority_flag_types(left, right):
    assert not service._same({"flag": left}, {"flag": right})


def test_canonical_comparison_ignores_key_order_only():
    assert service._same({"a": 1, "b": False}, {"b": False, "a": 1})


def test_cli_default_plan_no_io_or_execution_import(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.underlying_support_revalidation_cli import main

    original = builtins.__import__

    def guarded(module, *args, **kwargs):
        if module in {"duckdb", "nse_quant.data_platform.underlying_support_revalidation"}:
            raise AssertionError("Plan imported execution")
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--identity-db",
                str(tmp_path / "registry.duckdb"),
                "--bronze-db",
                str(tmp_path / "bronze.duckdb"),
                "--assertion-id",
                "a" * 64,
                "--request-file",
                str(tmp_path / "request.json"),
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
