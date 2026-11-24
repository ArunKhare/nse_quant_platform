"""Explicit opt-in real Quack tests; never opens operational files."""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import os
import socket
import time
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NSE_RUN_QUACK_INTEGRATION") != "1",
    reason="explicit temporary Quack integration opt-in required",
)


def _server(port, status, stop):
    import duckdb

    from nse_quant.market_data.quack_snapshot_boundary import (
        SnapshotPublisher,
        serve,
    )

    conn = duckdb.connect(":memory:")
    uri = None
    generation = 0

    try:
        publisher = SnapshotPublisher(conn)
        publisher.initialize()

        def publish():
            nonlocal generation
            next_generation = generation + 1
            now = datetime.now(UTC)
            capture_id = str(next_generation)
            common = dict(
                capture_id=capture_id,
                source_time=now.isoformat(),
                received_at=now.isoformat(),
            )
            snapshot = dict(
                version=1,
                underlying="NIFTY",
                capture_id=capture_id,
                captured_at=now.isoformat(),
                spot=dict(common, price=100),
                quotes=[dict(common, token=token, bid=2, ask=3) for token in (1, 2)],
            )
            publisher.publish(
                snapshot,
                underlying="NIFTY",
                expected_tokens=frozenset({1, 2}),
                as_of=now,
                max_age=timedelta(seconds=10),
            )
            generation = next_generation

        publish()
        uri, token = serve(conn, port=port)
        status.send(("ready", uri, token))

        while not stop.wait(0.05):
            publish()

        status.send(("stopped", generation))

    except BaseException as exc:
        # Report the type only; do not accidentally expose the token.
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            status.send(("failed", type(exc).__name__))
        raise

    finally:
        try:
            if uri is not None:
                conn.execute("CALL quack_stop(?)", [uri])
        finally:
            conn.close()
            status.close()


def _reader(uri, token, output):
    from nse_quant.market_data.market_snapshot_service import read_snapshot
    from nse_quant.market_data.quack_snapshot_boundary import connect_reader

    conn = None
    try:
        conn = connect_reader(uri, token)
        seen: set[str] = set()
        deadline = time.monotonic() + 12

        def read():
            return read_snapshot(
                conn,
                underlying="NIFTY",
                expected_tokens=frozenset({1, 2}),
                clock=lambda: datetime.now(UTC),
                max_age=timedelta(seconds=5),
            )

        while time.monotonic() < deadline and len(seen) < 3:
            snapshot = read()
            seen.add(snapshot["capture_id"])
            assert len(snapshot["quotes"]) == 2
            time.sleep(0.1)

        assert len(seen) >= 3, f"reader observed fewer than three captures: {sorted(seen)!r}"

        for sql in (
            "DELETE FROM market_snapshot_slot",
            "SELECT * FROM market_snapshot_slot",
        ):
            try:
                conn.execute(sql).fetchall()
            except Exception:
                pass
            else:
                raise AssertionError("unauthorized SQL succeeded")

        # The authorized path must remain usable after the rejected requests.
        read()
        output.put(("passed", len(seen)))

    except BaseException as exc:
        detail = str(exc) if isinstance(exc, AssertionError) else "reader operation failed"
        output.put(("failed", type(exc).__name__, detail))
        raise

    finally:
        if conn is not None:
            conn.close()


def _wrong_token(uri, token, output):
    from nse_quant.market_data.market_snapshot_service import READ_SQL
    from nse_quant.market_data.quack_snapshot_boundary import connect_reader

    wrong = ("A" if token[0] != "A" else "B") + token[1:]
    conn = None
    try:
        conn = connect_reader(uri, wrong)
        conn.execute(READ_SQL).fetchall()
    except Exception:
        output.put("rejected")
    else:
        output.put("accepted")
    finally:
        if conn is not None:
            conn.close()


def test_real_quack_publication_and_authorization():
    ctx = mp.get_context("spawn")
    status_recv, status_send = ctx.Pipe(duplex=False)
    output = ctx.Queue()
    stop = ctx.Event()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = ctx.Process(
        target=_server,
        args=(port, status_send, stop),
    )
    children = []

    server.start()
    status_send.close()

    try:
        assert status_recv.poll(30), (
            f"server readiness timed out; alive={server.is_alive()}, exitcode={server.exitcode}"
        )
        message = status_recv.recv()
        # Do not include a successful readiness message in assertion output:
        # it contains the secret.
        assert message[0] == "ready", f"server startup failed: status={message[0]!r}"
        _, uri, token = message

        readers = [ctx.Process(target=_reader, args=(uri, token, output)) for _ in range(3)]
        for child in readers:
            child.start()
            children.append(child)

        results = [output.get(timeout=30) for _ in readers]
        assert all(result[0] == "passed" for result in results), results

        for child in readers:
            child.join(timeout=10)
            assert child.exitcode == 0

        wrong = ctx.Process(
            target=_wrong_token,
            args=(uri, token, output),
        )
        wrong.start()
        children.append(wrong)

        assert output.get(timeout=20) == "rejected"
        wrong.join(timeout=10)
        assert wrong.exitcode == 0

        # Confirm the server is still available after the wrong-token attempt.
        final_reader = ctx.Process(
            target=_reader,
            args=(uri, token, output),
        )
        final_reader.start()
        children.append(final_reader)

        result = output.get(timeout=30)
        assert result[0] == "passed", result
        final_reader.join(timeout=10)
        assert final_reader.exitcode == 0

        stop.set()
        assert status_recv.poll(20), "server shutdown status timed out"
        final = status_recv.recv()
        assert final[0] == "stopped", final
        assert final[1] >= 3, final

        server.join(timeout=10)
        assert server.exitcode == 0

    finally:
        stop.set()
        for child in [*children, server]:
            child.join(timeout=5)
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)

        status_recv.close()
        output.close()
        output.join_thread()
