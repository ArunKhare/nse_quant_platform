"""CLI entry point for the paper decision loop."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from uuid import uuid4

from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.integrations.kite_auth import get_authenticated_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.persistence.duckdb_store import DuckDBStore


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

    kite = get_authenticated_kite()
    KiteMarketDataProvider(kite)
    DuckDBStore()
    PaperBroker()
    KillSwitch()