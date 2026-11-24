"""Opt-in temporary-store Quack multi-process capability probe, never an operational server."""

from __future__ import annotations

import contextlib
import json
import multiprocessing as mp
import os
import secrets
import shutil
import socket
import tempfile
import time
from pathlib import Path
from typing import Any

import duckdb

READ_SQL = "SELECT generation, value FROM main.probe_state"
DENIED_SQL = "DELETE FROM main.probe_state"


def load_installed_quack(conn: Any) -> None:
    if int(duckdb.__version__.split(".")[0]) < 2:
        raise RuntimeError("DUCKDB_2_REQUIRED")
    conn.execute("SET autoinstall_known_extensions=false")
    conn.execute("SET autoload_known_extensions=false")
    extension = os.environ.get("NSE_QUANT_QUACK_EXTENSION")
    if extension:
        path = Path(extension).resolve(strict=True)
        if not path.is_file() or path.suffix != ".duckdb_extension":
            raise ValueError("REVIEWED_LOCAL_EXTENSION_REQUIRED")
        quoted = path.as_posix().replace("'", "''")
        conn.execute(f"LOAD '{quoted}'")
    else:
        conn.execute("LOAD quack")


def _server(root: str, uri: str, ready: Any, stop: Any) -> None:
    conn = None
    started = False
    try:
        conn = duckdb.connect(str(Path(root) / "probe.duckdb"))
        conn.execute("SET memory_limit='256MB'")
        conn.execute("SET threads=1")
        load_installed_quack(conn)
        conn.execute("CREATE TABLE probe_state(generation BIGINT, value BIGINT)")
        conn.execute("INSERT INTO probe_state VALUES (0,42)")
        # Exact SQL allowlist, not an unsafe SELECT/WITH-prefix filter. This is
        # a narrowly scoped protocol probe, NOT general production authorization.
        query = READ_SQL.replace("'", "''")
        conn.execute(f"CREATE MACRO probe_authorize(sid, query) AS (query = '{query}')")
        conn.execute("SET GLOBAL quack_authorization_function='probe_authorize'")
        token = secrets.token_urlsafe(32)
        conn.execute("CALL quack_serve(?, token => ?)", [uri, token]).fetchall()
        started = True
        ready.put(dict(status="ready", token=token, pid=os.getpid()))
        generation = 0
        while not stop.wait(0.05):
            generation += 1
            conn.execute("UPDATE probe_state SET generation=?", [generation])
        if conn.execute("SELECT value FROM probe_state").fetchall() != [(42,)]:
            raise RuntimeError("PROBE_STATE_WAS_MUTATED")
        ready.put(dict(status="server_stopped", generation=generation))
    except Exception:
        ready.put(dict(status="server_failed"))
    finally:
        if conn is not None:
            if started:
                with contextlib.suppress(Exception):
                    conn.execute("CALL quack_stop(?)", [uri])
            conn.close()


def _client(role: str, uri: str, token: str, output: Any) -> None:
    conn = None
    try:
        conn = duckdb.connect(":memory:")
        conn.execute("SET memory_limit='128MB'")
        conn.execute("SET threads=1")
        load_installed_quack(conn)
        samples = []
        for _ in range(4):
            row = conn.execute("SELECT * FROM quack_query(?, ?, token => ?)", [uri, READ_SQL, token]).fetchone()
            if row is None or row[1] != 42:
                raise RuntimeError("PROBE_READ_MISMATCH")
            samples.append(int(row[0]))
            time.sleep(0.08)
        if samples[-1] <= samples[0]:
            raise RuntimeError("NO_CONCURRENT_WRITER_PROGRESS")
        try:
            conn.execute("SELECT * FROM quack_query(?, ?, token => ?)", [uri, DENIED_SQL, token]).fetchall()
        except duckdb.Error:
            pass
        else:
            raise RuntimeError("PROBE_UNAUTHORIZED_WRITE_WAS_NOT_REJECTED")
        # The denial must leave the server healthy and the protected state intact.
        row = conn.execute("SELECT * FROM quack_query(?, ?, token => ?)", [uri, READ_SQL, token]).fetchone()
        if row is None or row[1] != 42:
            raise RuntimeError("SERVER_UNHEALTHY_AFTER_DENIAL")
        output.put(dict(status="client_passed", role=role, pid=os.getpid(), writer_progress=True))
    except Exception:
        output.put(dict(status="client_failed", role=role))
    finally:
        if conn is not None:
            conn.close()


def run_probe() -> dict[str, Any]:
    """All writes are restricted to a fresh temporary directory, never configured stores."""
    if int(duckdb.__version__.split(".")[0]) < 2:
        return dict(status="unavailable", reason="DUCKDB_2_REQUIRED", duckdb_version=duckdb.__version__)
    try:
        with duckdb.connect(":memory:") as conn:
            load_installed_quack(conn)
    except Exception:
        return dict(status="unavailable", reason="LOCAL_QUACK_LOAD_FAILED", duckdb_version=duckdb.__version__)
    ctx = mp.get_context("spawn")
    ready, output, stop = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = []
    root = None
    try:
        root = tempfile.mkdtemp(prefix="nse-quack-probe-")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        uri = f"quack:127.0.0.1:{port}"
        server = ctx.Process(target=_server, args=(root, uri, ready, stop))
        server.start()
        processes.append(server)
        initial = ready.get(timeout=20)
        if initial.get("status") != "ready":
            raise RuntimeError("SERVER_START_FAILED")
        for role in ("paper_reader", "dashboard", "research"):
            process = ctx.Process(target=_client, args=(role, uri, initial["token"], output))
            process.start()
            processes.append(process)
        results = [output.get(timeout=25) for _ in range(3)]
        stop.set()
        final = ready.get(timeout=15)
        for process in processes:
            process.join(timeout=10)
        if (
            any(r.get("status") != "client_passed" for r in results)
            or final.get("status") != "server_stopped"
            or any(p.is_alive() or p.exitcode != 0 for p in processes)
        ):
            raise RuntimeError("MULTIPROCESS_PROBE_FAILED")
        return dict(
            status="passed",
            duckdb_version=duckdb.__version__,
            clients=results,
            server_pid=initial["pid"],
            writer_generation=final["generation"],
            operational_wiring_validated=False,
            decision_eligibility_asserted=False,
        )
    except Exception:
        return dict(
            status="failed",
            reason="QUACK_MULTIPROCESS_PROBE_FAILED",
            duckdb_version=duckdb.__version__,
            operational_wiring_validated=False,
        )
    finally:
        stop.set()
        for process in processes:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
        for queue in (ready, output):
            queue.close()
            queue.join_thread()
        if root is not None:
            shutil.rmtree(root)


def main() -> int:
    report = run_probe()
    print(json.dumps(report, sort_keys=True))
    return {"passed": 0, "unavailable": 3, "failed": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
