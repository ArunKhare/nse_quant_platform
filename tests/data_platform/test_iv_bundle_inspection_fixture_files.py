"""Real synthetic SQL snapshot/binding regression; no successful native computation mock."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments


@pytest.fixture
def synthetic_case(tmp_path):
    sources = [duckdb.connect(":memory:") for _ in range(4)]
    gold = duckdb.connect(":memory:")
    archive = duckdb.connect(str(tmp_path / "member.duckdb"))
    target = duckdb.connect(str(tmp_path / "bundle.duckdb"))
    handles = (*sources, gold, archive, target)
    for index, conn in enumerate(handles):
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        catalog = '"' + str(row[0]).replace('"', '""') + '"'
        conn.execute(f'CREATE SCHEMA {catalog}."fixture"')
        conn.execute(f'CREATE TABLE {catalog}."fixture"."rows" (value INTEGER PRIMARY KEY)')
        conn.execute(f'INSERT INTO {catalog}."fixture"."rows" VALUES (?)', [index])
    case = (
        target,
        None,
        None,
        {"build_id": "a" * 64},
        SimpleNamespace(evidence_fingerprint="b" * 64),
        sources,
        gold,
        archive,
        None,
        None,
    )
    yield case, handles
    for conn in handles:
        conn.close()


def test_memory_sources_snapshot_to_real_files_preserves_values_and_original_owners(synthetic_case):
    case, original = synthetic_case
    names = tuple("role-" + str(index) for index in range(7))
    args, paths = fixture_arguments(case, names)
    assert len(paths) == 7 and len(set(paths)) == 7
    assert args[-1] == "--execute"
    assert all(Path(path).is_file() for path in paths)
    for index, path in enumerate(paths):
        with duckdb.connect(path, read_only=True) as conn:
            row = conn.execute("SELECT current_database()").fetchone()
            assert row is not None
            catalog = '"' + str(row[0]).replace('"', '""') + '"'
            row = conn.execute(f'SELECT value FROM {catalog}."fixture"."rows"').fetchone()
            assert row == (index,)
    for conn in original[:5]:
        assert conn.execute("SELECT 1").fetchone() == (1,)
    for conn in original[5:]:
        with pytest.raises(duckdb.Error):
            conn.execute("SELECT 1")


@pytest.mark.parametrize("fail", [False, True], ids=["normal", "exception"])
def test_actual_open_handles_rebind_exact_source_identity_then_restore(
    synthetic_case,
    monkeypatch,
    fail,
):
    case, original = synthetic_case
    sources = case[5]
    _, paths = fixture_arguments(case, tuple("role-" + str(index) for index in range(7)))

    @contextmanager
    def real_open(selected):
        with ExitStack() as stack:
            handles = tuple(
                stack.enter_context(duckdb.connect(path, read_only=True)) for path in selected
            )
            yield handles

    diagnostic_boundary = SimpleNamespace(_open_inputs=real_open)
    with bind_fixture_sources(diagnostic_boundary, sources, monkeypatch):
        try:
            with diagnostic_boundary._open_inputs(tuple(paths)) as handles:
                # Retain the SAME assertion as the actual inspected source fixture.
                assert list(handles[:4]) == sources
                assert sources != list(original[:4])
                if fail:
                    raise RuntimeError("SYNTHETIC_FAILURE")
        except RuntimeError:
            assert fail
        assert sources == list(original[:4])
    assert diagnostic_boundary._open_inputs is real_open


def test_snapshot_does_not_invent_file_backed_archive(tmp_path):
    handles = [duckdb.connect(":memory:") for _ in range(7)]
    case = (
        handles[6],
        None,
        None,
        {"build_id": "a" * 64},
        SimpleNamespace(evidence_fingerprint="b" * 64),
        handles[:4],
        handles[4],
        handles[5],
        None,
        None,
    )
    try:
        with pytest.raises(AssertionError):
            fixture_arguments(case, tuple(str(index) for index in range(7)))
        assert not list(tmp_path.iterdir())
    finally:
        for conn in handles:
            conn.close()


def test_targeted_source_transform_keeps_unrelated_test_assertions(tmp_path):
    import runpy

    tool = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/qa/repair_iv_bundle_inspection_tests.py")
    )
    boundary = """import json
from test_example import fixture as fixture

def readonly_arguments(case):
    paths = []
    rows = conn.execute("PRAGMA database_list").fetchall()
    conn.close()
    return paths

def test_preserved():
    assert "ORIGINAL_STRICT_ASSERTION" == "ORIGINAL_STRICT_ASSERTION"
"""
    repaired = tool["transform_boundary"](boundary)
    assert 'assert "ORIGINAL_STRICT_ASSERTION" == "ORIGINAL_STRICT_ASSERTION"' in repaired
    assert "return fixture_arguments(case, cli.PATH_NAMES)" in repaired
    assert "@pytest.fixture(autouse=True)" in repaired
    compile(repaired, "synthetic edited source", "exec")
    with pytest.raises(ValueError):
        tool["transform_boundary"](repaired)
    source = """def arguments():
    result = []
    return result

def test_bundle_archive_source_alias_rejected_before_connection():
    with pytest.raises(ValueError, match="SEPARATE_IV_BUNDLE_ARCHIVE"):
        with cli._open_inputs(tuple(paths)):
            raise AssertionError("Unexpected context entry")

def test_member_archive_source_alias_rejected():
    with pytest.raises(ValueError, match="SEPARATE_IV_MEMBER_ARCHIVE"):
        with cli._open_inputs(tuple(paths)):
            raise AssertionError("Unexpected context entry")
"""
    edited = tool["transform_cli_test"](source)
    assert "result: list[str] = []" in edited
    assert edited.count('raise AssertionError("Unexpected context entry")') == 2
    assert edited.count("    with (\n") == 2
    compile(edited, "synthetic edited CLI test", "exec")
    import hashlib

    for name, raw in ((tool["BOUNDARY"], boundary), (tool["CLI_TEST"], source)):
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(raw, encoding="utf-8")
    old_manifest = "".join(
        hashlib.sha256(raw.encode()).hexdigest() + "  " + name + "\n"
        for name, raw in ((tool["BOUNDARY"], boundary), (tool["CLI_TEST"], source))
    )
    old_manifest += "c" * 64 + "  unrelated-preserved.py\n"
    (tmp_path / tool["MANIFEST"]).write_text(old_manifest, encoding="utf-8")
    changes = tool["prepare"](tmp_path)
    assert len(changes) == 3
    for name in (tool["BOUNDARY"], tool["CLI_TEST"]):
        assert hashlib.sha256(changes[name]).hexdigest().encode() in changes[tool["MANIFEST"]]
    assert ("c" * 64 + "  unrelated-preserved.py").encode() in changes[tool["MANIFEST"]]
    assert (tmp_path / tool["MANIFEST"]).read_text() == old_manifest
