"""Run the paper decision loop and Dash console in one process."""

from __future__ import annotations

import argparse
import threading
import time
from uuid import uuid4

from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.live_snapshot import build_snapshot, write_live_snapshot
from nse_quant.ops.notifier import Notifier
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.strategy.decision_loop import DecisionLoop
from nse_quant.ui.dash_app import app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run NSE Quant paper loop and Dash console together"
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=300,
        help="Paper-loop duration in seconds",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional settings YAML path",
    )
    parser.add_argument(
        "--reset-kill-switch",
        action="store_true",
        help="Reset the persistent kill switch before starting",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    if settings.safety.trading_enabled:
        raise RuntimeError(
            "Live trading is blocked in v0.3.0. Set TRADING_ENABLED=false."
        )

    store = DuckDBStore()
    kill_switch = KillSwitch()

    if args.reset_kill_switch:
        kill_switch.reset("platform_manual_reset")
        print("Kill switch reset.")

    kite = get_cached_kite(settings=settings)
    provider = KiteMarketDataProvider(kite)
    broker = PaperBroker()
    notifier = Notifier()
    run_id = uuid4().hex

    loop = DecisionLoop(
        store=store,
        provider=provider,
        broker=broker,
        run_id=run_id,
        settings=settings,
    )

    def run_dashboard() -> None:
        app.run(
            host=settings.storage.dashboard_host,
            port=settings.storage.dashboard_port,
            debug=False,
        )

    dashboard_thread = threading.Thread(
        target=run_dashboard,
        name="dash-server",
        daemon=True,
    )
    dashboard_thread.start()

    print(
        f"Dashboard: http://{settings.storage.dashboard_host}:"
        f"{settings.storage.dashboard_port}"
    )
    print("Starting paper decision loop...")

    end_time = time.monotonic() + args.seconds

    try:
        while time.monotonic() < end_time:
            if kill_switch.is_active():
                write_live_snapshot(
                    build_snapshot(
                        kill_switch_active=True,
                        loop_status="kill_switch_active",
                    )
                )
                print("Kill switch active. Paper loop stopped.")
                notifier.send("NSE Quant: kill switch active; loop stopped.")
                break

            result = loop.run_once()
            print(result)

            status = result.get("status")

            if status in {"risk_rejected", "dry_run"}:
                reasons = ", ".join(result.get("reasons", []))
                notifier.send(
                    f"NSE Quant: {status} {reasons}".strip()
                )

            time.sleep(settings.runtime.loop_interval_seconds)

    except KeyboardInterrupt:
        print("Platform interrupted.")

    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())