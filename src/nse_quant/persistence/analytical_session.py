"""Process-owned, resource-bounded analytical reads of pinned immutable Parquet.

This is not an operational database adapter, publisher or decision authority.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

ROLES = frozenset({"dashboard", "research", "backtest", "normalizer", "gold_builder", "replay", "paper_reader"})


@dataclass(frozen=True)
class AnalyticalBudget:
    memory_mb: int = 256
    threads: int = 1
    max_rows: int = 10000

    def __post_init__(self) -> None:
        for value, low, high in ((self.memory_mb, 32, 65536), (self.threads, 1, 64), (self.max_rows, 1, 100000)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("STRICT_ANALYTICAL_BUDGET_REQUIRED")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


class AnalyticalSession:
    """One explicitly owned in-memory session; no mutable operational file opens.

    Supply a configured TRADING_DATA_ROOT explicitly, or through the environment.
    The caller must close the session. Objects must not cross process boundaries.
    This is an application contract, not an untrusted-SQL sandbox.
    """

    def __init__(self, *, role: str, data_root: Path | None = None, budget: AnalyticalBudget | None = None):
        if role not in ROLES:
            raise ValueError("EXPLICIT_ANALYTICAL_ROLE_REQUIRED")
        configured = data_root if data_root is not None else os.environ.get("TRADING_DATA_ROOT")
        if configured is None or not str(configured).strip():
            raise ValueError("TRADING_DATA_ROOT_REQUIRED")
        self.root = Path(configured).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("DATA_ROOT_DIRECTORY_REQUIRED")
        self.pid = os.getpid()
        self.role = role
        self.budget = budget or AnalyticalBudget()
        self.closed = False
        scratch = self.root / "tmp_duckdb"
        scratch.mkdir(exist_ok=True)
        if scratch.is_symlink():
            raise ValueError("OWNED_SPILL_DIRECTORY_REQUIRED")
        self.spill = Path(tempfile.mkdtemp(prefix=f"{role}-{self.pid}-", dir=scratch))
        try:
            self._conn = duckdb.connect(":memory:")
            self._conn.execute(f"SET memory_limit='{self.budget.memory_mb}MB'")
            self._conn.execute(f"SET threads={self.budget.threads}")
            spill = self.spill.as_posix().replace("'", "''")
            self._conn.execute(f"SET temp_directory='{spill}'")
            self._conn.execute("SET autoinstall_known_extensions=false")
            self._conn.execute("SET autoload_known_extensions=false")
        except BaseException:
            if hasattr(self, "_conn"):
                self._conn.close()
            shutil.rmtree(self.spill)
            raise

    def _owned(self) -> None:
        if os.getpid() != self.pid:
            raise RuntimeError("CROSS_PROCESS_CONNECTION_FORBIDDEN")
        if self.closed:
            raise RuntimeError("ANALYTICAL_SESSION_CLOSED")

    def read_pinned(self, path: Path, *, expected_sha256: str) -> tuple[tuple[Any, ...], ...]:
        self._owned()
        if re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
            raise ValueError("EXACT_PARQUET_PIN_REQUIRED")
        path = Path(path)
        if path.is_symlink():
            raise ValueError("IMMUTABLE_REGULAR_FILE_REQUIRED")
        path = path.resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".parquet" or not path.is_relative_to(self.root):
            raise ValueError("PINNED_PARQUET_UNDER_DATA_ROOT_REQUIRED")
        if file_sha256(path) != expected_sha256:
            raise ValueError("PARQUET_PIN_MISMATCH")
        before = path.stat()
        rows = self._conn.execute(
            "SELECT * FROM read_parquet(?) LIMIT ?", [str(path), self.budget.max_rows + 1]
        ).fetchall()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("IMMUTABLE_SOURCE_CHANGED")
        if file_sha256(path) != expected_sha256:
            raise ValueError("IMMUTABLE_SOURCE_CHANGED")
        if len(rows) > self.budget.max_rows:
            raise ValueError("ANALYTICAL_RESULT_BOUND_EXCEEDED")
        return tuple(tuple(row) for row in rows)

    def close(self) -> None:
        if os.getpid() != self.pid:
            raise RuntimeError("CROSS_PROCESS_CONNECTION_FORBIDDEN")
        if not self.closed:
            self._conn.close()
            self.closed = True
            shutil.rmtree(self.spill)

    def __getstate__(self) -> Any:
        raise TypeError("PROCESS_LOCAL_SESSION_MUST_NOT_BE_SERIALIZED")

    def __enter__(self) -> AnalyticalSession:
        self._owned()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
