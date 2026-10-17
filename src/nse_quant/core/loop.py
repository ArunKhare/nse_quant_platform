"""CLI entry point for the paper decision loop."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from uuid import uuid4

from nse_quant.core.market_calendar import is_market_open_now
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.notifier import Notifier
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import DecisionRepository
from nse_quant.strategy.decision_loop import DecisionLoop


def _record_kill_switch(store: DuckDBStore, run_id: str) -> None:
    store.conn.execute(
        """
        INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            uuid4().hex,
            datetime.now(UTC),
            run_id,
            "kill_switch_active",
            None,
            None,
            None,
            None,
            '{"reason":"cli_or_dashboard_kill_switch"}',
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the NSE Quant paper decision loop"
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=120,
        help="Duration to run the loop",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional settings YAML path",
    )
    args = parser.parse_args()

    settings = get_settings(args.config)

    if settings.safety.trading_enabled:
        raise RuntimeError(
            "Live trading is blocked in v0.3.0. Set TRADING_ENABLED=false."
        )

    print("Starting NSE Quant paper decision loop...")
    print(
        f"DRY_RUN={settings.safety.dry_run}, "
        f"TRADING_ENABLED={settings.safety.trading_enabled}, "
        f"PAPER_TRADING={settings.safety.paper_trading}"
    )

    kite = get_cached_kite(settings=settings)
    provider = KiteMarketDataProvider(kite)
    store = DuckDBStore()
    broker = PaperBroker()
    kill_switch = KillSwitch()
    notifier = Notifier()
    run_id = uuid4().hex

    loop = DecisionLoop(
        store=store,
        provider=provider,
        broker=broker,
        run_id=run_id,
        settings=settings,
    )

    end_time = time.monotonic() + args.seconds

    try:
        while time.monotonic() < end_time:
            if is_market_open_now():
                print("Market is open. Continuing loop.")
            else:
                print("NSE Market is closed. waiting...")
                time.sleep(60)
                continue
            if kill_switch.is_active():
                _record_kill_switch(store, run_id)
                print("Kill switch active. Paper loop stopped.")
                notifier.send("NSE Quant: kill switch active; loop stopped.")
                break

            try:
                result = loop.run_once()
                print(result)
            except Exception as exc: #noqa:BLE001
                result = {
                    "status": "loop_error",
                    "error": str(exc),
                }
                print(result)
                notifier.send(f"NSE Quant loop error: {exc}")
                decision_repo = DecisionRepository(store)
                decision_repo.save_system_event(
                    run_id,
                    event_type='loop_error',
                    payload={
                        "error": str(exc),
                        "error_type": type(exc).__name__
                        },
                    )
            status = result.get("status")

            if status in {"risk_rejected", "dry_run"}:
                reasons = ", ".join(result.get("reasons", []))
                notifier.send(
                    f"NSE Quant: {status} {reasons}".strip()
                )

            time.sleep(settings.runtime.loop_interval_seconds)

    except KeyboardInterrupt:
        print("Paper loop interrupted.")

    finally:
        store.close()

    print("Paper decision loop finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())