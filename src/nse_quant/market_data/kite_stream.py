"""Read-only bounded Kite WebSocket runner."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kiteconnect import KiteTicker

from nse_quant.analytics.option_analytics import enrich_quote
from nse_quant.integrations.kite_auth import get_authenticated_kite

from ..core.settings import get_settings
from ..market_data.kite_provider import KiteMarketDataProvider
from ..market_data.normalizer import normalize_tick
from ..persistence.duckdb_store import DuckDBStore


def atomic_write(
    path: Path,
    payload: dict[str, Any],
    retries: int = 3,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=path.parent)

    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(
                payload,
                handle,
                default=str,
            )

        for attempt in range(retries):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == retries - 1:
                    raise

                time.sleep(0.2)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument(
        "--seconds",
        type=int,
        default=120
        )
    args=parser.parse_args()
    settings=get_settings()

    kite=get_authenticated_kite()
    provider=KiteMarketDataProvider(kite)

    snapshots = provider.get_chain_snapshots()
    snapshot_ts = datetime.now(UTC)

    for snapshot in snapshots:
        snapshot.ts = snapshot_ts

    tokens=sorted(
        {quote.instrument_token
         for snapshot in snapshots
         for quote in snapshot.quotes
         }
    )
    state: dict[int, dict[str, Any]] = {}
    lock=threading.Lock()
    connected=threading.Event()

    ws=KiteTicker(
        settings.secrets.kite_api_key,
        kite.access_token,
        )

    def on_connect(client, response):
        client.subscribe(tokens)
        client.set_mode(client.MODE_FULL, tokens)
        connected.set()

    ws.on_connect = on_connect

    def on_ticks(c,ticks):
        now=datetime.now(UTC)
        with lock:
            for t in ticks:
                state[
                    int(t["instrument_token"])
                    ] = normalize_tick(t,now).model_dump(mode="json")

    ws.on_ticks = on_ticks
    ws.on_error = lambda *a: connected.clear()
    ws.on_close = lambda *a: connected.clear()

    store = DuckDBStore()
    run_id = uuid.uuid4().hex
    ws.connect(threaded=True)
    end = time.monotonic() + args.seconds

    try:
        while time.monotonic() < end:
            time.sleep(1)
            with lock:
                current=dict(state)
            now = datetime.now()
            for snapshot in snapshots:
                print(snapshot)
                for quote in snapshot.quotes:
                    enrich_quote(
                        quote=quote,
                        spot=snapshot.spot,
                        expiry=snapshot.expiry,
                        now=now,
                        rate=settings.analytics.risk_free_rate
                    )

                store.write_option_stream(
                    run_id,
                    snapshot,
                    current,
                )

            atomic_write(
                Path("market_data/latest_stream.json"),
                {
                    "run_id": run_id,
                    "connected": connected.is_set(),
                    "ticks": len(current),
                    "expiries": len(snapshots),
                },
            )

    except KeyboardInterrupt: pass
    finally:
        ws.close(); store.close()
    return 0

if __name__=="__main__": raise SystemExit(main())
