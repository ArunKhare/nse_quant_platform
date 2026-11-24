"""Critical ownership/IPC tests; spawned fixture roles, never real app runners."""

from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import time
from pathlib import Path

import duckdb
import pytest

from nse_quant.persistence.analytical_session import AnalyticalBudget, AnalyticalSession, file_sha256
from nse_quant.persistence.quack_probe import run_probe


def _fixture_writer(root, ready, stop):
    with duckdb.connect(str(Path(root) / "writer.duckdb")) as conn:
        conn.execute("SET threads=1")
        conn.execute("CREATE TABLE state AS SELECT 0 AS generation")
        path = Path(root) / "published.parquet"
        escaped = str(path).replace("'", "''")
        conn.execute(f"COPY (SELECT 42 AS value) TO '{escaped}' (FORMAT PARQUET)")
        ready.put((str(path), file_sha256(path), os.getpid()))
        generation = 0
        while not stop.wait(0.02):
            generation += 1
            conn.execute("UPDATE state SET generation=?", [generation])
        ready.put(generation)


def _fixture_reader(root, path, pin, role, output):
    try:
        with AnalyticalSession(role=role, data_root=Path(root)) as session:
            for _ in range(4):
                assert session.read_pinned(Path(path), expected_sha256=pin) == ((42,),)
                time.sleep(0.02)
        output.put((role, os.getpid(), "passed"))
    except Exception:
        output.put((role, os.getpid(), "failed"))


def _stop(processes, event):
    event.set()
    for process in processes:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_spawned_writer_and_three_snapshot_readers(tmp_path):
    ctx = mp.get_context("spawn")
    ready, output, stop = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = []
    try:
        writer = ctx.Process(target=_fixture_writer, args=(str(tmp_path), ready, stop))
        writer.start()
        processes.append(writer)
        path, pin, writer_pid = ready.get(timeout=15)
        for role in ("paper_reader", "dashboard", "research"):
            process = ctx.Process(target=_fixture_reader, args=(str(tmp_path), path, pin, role, output))
            process.start()
            processes.append(process)
        results = [output.get(timeout=20) for _ in range(3)]
        assert all(row[2] == "passed" for row in results)
        assert len({writer_pid, *(row[1] for row in results)}) == 4
        stop.set()
        assert ready.get(timeout=10) > 0
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert file_sha256(Path(path)) == pin
    finally:
        _stop(processes, stop)
        for queue in (ready, output):
            queue.close()
            queue.join_thread()


def test_readonly_does_not_bypass_other_process_native_writer_lock(tmp_path):
    ctx = mp.get_context("spawn")
    ready, stop = ctx.Queue(), ctx.Event()
    writer = ctx.Process(target=_fixture_writer, args=(str(tmp_path), ready, stop))
    writer.start()
    try:
        ready.get(timeout=15)
        with pytest.raises(duckdb.Error):
            duckdb.connect(str(tmp_path / "writer.duckdb"), read_only=True)
    finally:
        _stop([writer], stop)
        ready.close()
        ready.join_thread()


@pytest.mark.parametrize(
    "kwargs", [{"threads": True}, {"threads": 0}, {"memory_mb": 1}, {"memory_mb": "256"}, {"max_rows": 0}]
)
def test_strict_resource_budgets(kwargs):
    with pytest.raises(ValueError):
        AnalyticalBudget(**kwargs)


def _parquet(path, rows=1):
    with duckdb.connect(":memory:") as conn:
        escaped = str(path).replace("'", "''")
        conn.execute(f"COPY (SELECT * FROM range({rows})) TO '{escaped}' (FORMAT PARQUET)")
    return file_sha256(path)


def test_pin_bound_close_and_process_ownership(tmp_path, monkeypatch):
    path = tmp_path / "data.parquet"
    pin = _parquet(path, rows=2)
    session = AnalyticalSession(role="research", data_root=tmp_path, budget=AnalyticalBudget(max_rows=1))
    spill = session.spill
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        session.read_pinned(path, expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="BOUND_EXCEEDED"):
        session.read_pinned(path, expected_sha256=pin)
    with pytest.raises(TypeError, match="SERIALIZED"):
        pickle.dumps(session)
    with monkeypatch.context() as patch:
        patch.setattr(os, "getpid", lambda: session.pid + 1)
        with pytest.raises(RuntimeError, match="CROSS_PROCESS"):
            session.read_pinned(path, expected_sha256=pin)
        with pytest.raises(RuntimeError, match="CROSS_PROCESS"):
            session.close()
    session.close()
    session.close()
    assert not spill.exists()
    with pytest.raises(RuntimeError, match="CLOSED"):
        session.read_pinned(path, expected_sha256=pin)


def test_explicit_root_and_role_required(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADING_DATA_ROOT", raising=False)
    with pytest.raises(ValueError, match="TRADING_DATA_ROOT_REQUIRED"):
        AnalyticalSession(role="research")
    with pytest.raises(ValueError, match="ROLE_REQUIRED"):
        AnalyticalSession(role="unowned", data_root=tmp_path)


def test_independent_spill_and_reading_without_source_mutation(tmp_path):
    path = tmp_path / "data.parquet"
    pin = _parquet(path)
    with (
        AnalyticalSession(role="research", data_root=tmp_path) as first,
        AnalyticalSession(role="dashboard", data_root=tmp_path) as second,
    ):
        assert first.spill != second.spill
        assert first.read_pinned(path, expected_sha256=pin) == second.read_pinned(path, expected_sha256=pin)
    assert file_sha256(path) == pin


@pytest.mark.skipif(os.environ.get("NSE_QUANT_VALIDATE_QUACK") != "1", reason="explicit local Quack probe opt-in")
def test_quack_server_three_clients_and_writer_progress():
    result = run_probe()
    if result["status"] == "unavailable":
        pytest.fail("Quack opt-in requested but runtime/installed extension unavailable")
    assert result["status"] == "passed", result
    assert len(result["clients"]) == 3
    assert result["operational_wiring_validated"] is False
