"""Test-only disposable memory snapshots and exact lower-boundary handle rebinding."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def fixture_arguments(case: Any, names: tuple[str, ...]) -> tuple[list[str], list[str]]:
    target, _, _, receipt, reviewed, sources, gold, archive, _, _ = case
    handles = (*sources, gold, archive, target)
    assert len(handles) == len(names) == 7
    metadata: list[tuple[Any, str, str | None]] = []
    for conn in handles:
        row = conn.execute("SELECT current_database()").fetchone()
        assert row is not None
        catalog = str(row[0])
        selected = [
            item[2]
            for item in conn.execute("PRAGMA database_list").fetchall()
            if item[1] == catalog
        ]
        assert len(selected) == 1
        path = selected[0]
        assert path is None or isinstance(path, str)
        metadata.append((conn, catalog, path))
    # The two real archive fixtures MUST already be file-backed; never invent them.
    assert metadata[5][2] and metadata[6][2]
    directory = Path(str(metadata[6][2])).parent
    snapshots: dict[tuple[int, str], str] = {}
    paths: list[str] = []
    for index, (conn, catalog, original) in enumerate(metadata):
        if original:
            paths.append(original)
            continue
        key = (id(conn), catalog)
        if key not in snapshots:
            destination = directory / ("inspection_fixture_" + str(index) + ".duckdb")
            assert not destination.exists()
            alias = quote_identifier("__iv_inspection_export_" + str(index))
            escaped = str(destination).replace("'", "''")
            conn.execute(f"ATTACH '{escaped}' AS {alias}")
            try:
                conn.execute(f"COPY FROM DATABASE {quote_identifier(catalog)} TO {alias}")
            finally:
                conn.execute(f"DETACH {alias}")
            assert destination.is_file()
            snapshots[key] = str(destination)
        paths.append(snapshots[key])
    # Close actual file-backed owners before reopening with a different read_only config.
    # Keep original memory owners alive for existing fixture closures and teardown.
    closed: set[int] = set()
    for conn, _, original in metadata:
        if original and id(conn) not in closed:
            conn.close()
            closed.add(id(conn))
    args: list[str] = []
    for name, path in zip(names, paths, strict=True):
        args.extend(("--" + name, path))
    args.extend(
        (
            "--build-id-pin",
            receipt["build_id"],
            "--archive-fingerprint",
            reviewed.evidence_fingerprint,
            "--execute",
        )
    )
    return args, paths


@contextmanager
def bind_fixture_sources(cli: Any, sources: list[Any], monkeypatch: Any) -> Iterator[None]:
    """Preserve the existing source substitute AND its exact handle-identity assertion.

    Instrument only the actual CLI connection context. No reader/model/result is
    substituted. Actual reopened read-only source-role handles become the fixture's
    expected handles only during execution, then original memory owners are restored.
    """
    real_open = cli._open_inputs

    @contextmanager
    def rebound(paths: tuple[str, ...]) -> Iterator[tuple[Any, ...]]:
        with real_open(paths) as handles:
            original = sources[:]
            assert len(original) == 4 and len(handles) == 7
            sources[:] = handles[:4]
            try:
                yield handles
            finally:
                sources[:] = original

    with monkeypatch.context() as patch:
        patch.setattr(cli, "_open_inputs", rebound)
        yield
