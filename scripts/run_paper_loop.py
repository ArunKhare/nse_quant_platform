"""Run the paper decision loop.

This script never enables live trading. It uses PaperBroker only and respects
the persistent kill switch.
"""

from __future__ import annotations

import argparse
import time
from uuid import uuid4

from nse_quant.core.market_calendar import is_market_open_now
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.market_data.replay_provider import ReplayMarketDataProvider
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.notifier import Notifier, NullNotifier
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.repositories import DecisionRepository
from nse_quant.strategy.decision_loop import DecisionLoop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NSE Quant paper loop")
    parser.add_argument(
        "--seconds",
        type=int,
        default=120,
        help="Duration to run the loop",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to settings YAML",
    )
    parser.add_argument(
        "--allow-out-of-hours",
        action="store_true",
        help="Allow strategy testing while NSE is closed",
    )
    parser.add_argument(
        "--replay-file",
        default=None,
        help="Run the decision loop against a saved snapshot replay",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    if args.allow_out_of_hours:
        settings.runtime.allow_out_of_hours_testing = True
    if settings.safety.trading_enabled:
        raise RuntimeError(
            "Live trading is blocked in v0.3.0. Set TRADING_ENABLED=false."
        )
    if args.replay_file:
        provider = ReplayMarketDataProvider.from_json(args.replay_file)
    else:
        kite = get_cached_kite(settings=settings)
        provider = KiteMarketDataProvider(kite)
    store = DuckDBStore()
    broker = PaperBroker()
    kill_switch = KillSwitch()
    notifier = Notifier() if settings.notifier.enabled else NullNotifier()
    run_id = uuid4().hex
    decision= DecisionRepository(store.conn)

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
            if kill_switch.is_active():
                loop.handle_kill_switch()
                print("Kill switch active. Paper loop stopped.")
                notifier.send("NSE Quant: kill switch active; loop stopped.")
                break
            if not is_market_open_now() and not settings.runtime.allow_out_of_hours_testing:
                print("NSE Market is closed. Waiting...")
                time.sleep(settings.runtime.market_closed_wait_seconds)
                continue
            if not is_market_open_now() and settings.runtime.allow_out_of_hours_testing:
                print(
                    "NSE Market is closed. "
                    "Out-of-hours strategy testing enabled."
                )
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
                decision.save_system_event(
                    run_id,
                    event_type='loop_error',
                    payload={
                        "error": str(exc),
                        "error_type": type(exc).__name__
                        },
                    )

            if result.get("status") in {"risk_rejected", "dry_run"}:
                reasons = ", ".join(result.get("reasons", []))
                notifier.send(
                    f"NSE Quant: {result.get('status')} {reasons}".strip()
                )

            time.sleep(settings.runtime.loop_interval_seconds)

    except KeyboardInterrupt:
        print("Paper loop interrupted.")

    finally:
        store.conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())