"""Run the paper decision loop.

This script never enables live trading. It uses PaperBroker only and respects
the persistent kill switch.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from nse_quant.core.market_calendar import is_market_open_now
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.features.feature_gates import SpotFeatureGate
from nse_quant.integrations.kite_session import get_cached_kite
from nse_quant.market_data.kite_provider import KiteMarketDataProvider
from nse_quant.market_data.replay_provider import (
    ReplayExhaustedError,
    ReplayMarketDataProvider,
)
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
        help=("Run against a saved chain-snapshot replay JSON instead of live Kite data"),
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="Underlying symbol; repeat for multiple symbols",
    )
    parser.add_argument(
        "--warmup-from",
        dest="warmup_from",
        default=None,
        help=(
            "Optional ISO start datetime for explicit historical "
            "candle warm-up; no default lookback is applied"
        ),
    )
    parser.add_argument(
        "--warmup-to",
        dest="warmup_to",
        default=None,
        help=(
            "Optional ISO end datetime for explicit historical "
            "candle warm-up; required when --warmup-from is supplied"
        ),
    )
    parser.add_argument(
        "--allow-stale-features",
        action="store_true",
        help=(
            "Allow stale historical spot features during out-of-hours "
            "testing. Never use for live decision-making."
        ),
    )
    parser.add_argument(
        "--spot-token",
        type=int,
        default=None,
        help=("Spot instrument token used in replay mode; required when --replay-file is supplied"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    if args.allow_out_of_hours:
        settings.runtime.allow_out_of_hours_testing = True

    if settings.safety.trading_enabled:
        raise RuntimeError("Live trading is blocked in v0.3.0. Set TRADING_ENABLED=false.")

    if args.replay_file:
        provider = ReplayMarketDataProvider.from_json(
            args.replay_file,
            spot_instrument_tokens=(
                {settings.market_data.default_symbol: args.spot_token}
                if args.spot_token is not None
                else None
            ),
        )

        spot_token: int | None = args.spot_token

    else:
        kite = get_cached_kite(settings=settings)
        provider = KiteMarketDataProvider(kite)

        provider.underlying = settings.market_data.default_symbol

        spot_token = provider.resolve_spot_instrument_token(settings.market_data.default_symbol)

        print(
            "Live spot token:",
            settings.market_data.default_symbol,
            spot_token,
        )

    stale_seconds = int(getattr(settings.runtime, "stale_seconds", 50 * 60 * 60))

    feature_gate = SpotFeatureGate(
        max_age_seconds=(stale_seconds if not args.allow_stale_features else 7 * 24 * 60 * 60),
        index_symbols=tuple(settings.market_data.index_symbols),
    )

    warmup_from = datetime.fromisoformat(args.warmup_from) if args.warmup_from else None

    warmup_to = datetime.fromisoformat(args.warmup_to) if args.warmup_to else None

    if (warmup_from is None) != (warmup_to is None):
        raise ValueError("--warmup-from and --warmup-to must be supplied together")

    if warmup_from is not None and warmup_to is not None and warmup_to <= warmup_from:
        raise ValueError("--warmup-to must be later than --warmup-from")

    intervals = list(settings.market_data.candle_intervals)

    store = DuckDBStore()
    broker = PaperBroker()
    kill_switch = KillSwitch()
    notifier = Notifier() if settings.notifier.enabled else NullNotifier()
    run_id = uuid4().hex
    decision = DecisionRepository(store.conn)

    loop = DecisionLoop(
        store=store,
        provider=provider,
        broker=broker,
        run_id=run_id,
        settings=settings,
        feature_gate=feature_gate,
    )

    symbols: list[str] = args.symbol if args.symbol else [settings.market_data.default_symbol]

    primary_symbol = symbols[0]

    notifier.send(
        "NSE Quant paper loop started\n"
        f"Run ID: {run_id}\n"
        f"Symbol: {primary_symbol}\n"
        f"Duration: {args.seconds}s\n"
        f"Mode: {'replay' if args.replay_file else 'live-paper'}",
    )

    feature_snapshot = loop.feature_service.latest(primary_symbol)

    if feature_snapshot is not None:
        feature_age = datetime.now(UTC) - feature_snapshot.ts.tz_convert(UTC)

        print(
            "Latest feature:",
            feature_snapshot.ts,
            "age_seconds:",
            feature_age.total_seconds(),
        )

    print(
        "Gate max age seconds:",
        loop.feature_gate._max_age_seconds,
    )

    loop_failed = False
    failure_error: BaseException | None = None

    try:
        if (
            isinstance(provider, KiteMarketDataProvider)
            and warmup_from is not None
            and warmup_to is not None
        ):
            for symbol in symbols:
                if spot_token is None:
                    spot_token = provider.resolve_spot_instrument_token(primary_symbol)

                for interval in intervals:
                    candles = provider.get_historical_candles(
                        symbol=symbol,
                        interval=interval,
                        from_dt=warmup_from,
                        to_dt=warmup_to,
                    )

                    if not candles:
                        print(f"No candles: {symbol} {interval}")
                        continue

                    rows = store.write_spot_candles(
                        candles=candles,
                        symbol=symbol,
                        instrument_token=spot_token,
                        interval=interval,
                    )

                    print(f"{symbol} {interval}: fetched={len(candles)} persisted={rows}")

        elif warmup_from is None:
            print(
                "Skipping historical warm-up; supply --warmup-from and "
                "--warmup-to or pre-import candles with "
                "scripts/import_candle.py."
            )

        end_time = time.monotonic() + args.seconds
        result: dict[str, Any] = {}

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
                print("NSE Market is closed. Out-of-hours strategy testing enabled.")

            if isinstance(provider, KiteMarketDataProvider) and spot_token and is_market_open_now():
                try:
                    now = datetime.now(UTC)

                    candle_minute = now.replace(
                        second=0,
                        microsecond=0,
                    )

                    spot_price = provider.get_spot()

                    rows_written = store.write_spot_candles(
                        candles=[
                            {
                                "date": candle_minute,
                                "open": spot_price,
                                "high": spot_price,
                                "low": spot_price,
                                "close": spot_price,
                                "volume": 0,
                                "oi": None,
                            }
                        ],
                        symbol=primary_symbol,
                        instrument_token=spot_token,
                        interval="1m",
                    )

                    print(
                        "Persisted 1m candle:",
                        candle_minute,
                        "close:",
                        spot_price,
                        "rows:",
                        rows_written,
                    )

                    store.refresh_latest_spot_feature(
                        symbol=primary_symbol,
                        instrument_token=spot_token,
                        as_of=now,
                    )

                    status_path = Path("logs/live_status.json")
                    status_path.parent.mkdir(parents=True, exist_ok=True)

                    current_status = {}

                    if status_path.exists():
                        try:
                            current_status = json.loads(status_path.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            current_status = {}

                    current_status["candles_written_this_session"] = (
                        current_status.get("candles_written_this_session", 0) + rows_written
                    )

                    eligibility = result.get("strategy_eligibility", {})
                    features = result.get("features", {})

                    current_status.update(
                        {
                            "updated_at": datetime.now(UTC).isoformat(),
                            "symbol": primary_symbol,
                            "loop_status": result.get("status"),
                            "latest_candle": candle_minute.isoformat(),
                            "latest_close": spot_price,
                            "regime": features.get("regime"),
                            "realized_vol": features.get("realized_vol"),
                            "iv_rank": features.get("iv_rank"),
                            "strategy_eligibility": {
                                "passed": eligibility.get("passed"),
                                "reason": eligibility.get("reason"),
                            },
                            "open_positions": result.get("open_positions", []),
                            "latest_orders": result.get("latest_orders", []),
                            "latest_exits": result.get("latest_exits", []),
                        }
                    )

                    status_path.write_text(
                        json.dumps(current_status, indent=2, default=str),
                        encoding="utf-8",
                    )

                except Exception:  # noqa:BLE001
                    print("Spot candle capture failed:")
                    traceback.print_exc()

            try:
                result = loop.run_once()
                print(result)

            except ReplayExhaustedError:
                print("Replay exhausted. Paper loop stopped.")
                break

            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()

                result = {
                    "status": "loop_error",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

                print(result)
                notifier.send(f"NSE Quant loop error: {exc}")

                decision.save_system_event(
                    run_id,
                    event_type="loop_error",
                    payload={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

            if result.get("status") in {"risk_rejected", "dry_run"}:
                reasons = ", ".join(result.get("reasons", []))

                notifier.send(f"NSE Quant: {result.get('status')} {reasons}".strip())

            time.sleep(settings.runtime.loop_interval_seconds)

    except KeyboardInterrupt:
        print("Paper loop interrupted.")
        notifier.send(
            f"NSE Quant paper loop interrupted by user.\nRun ID: {run_id}",
        )
    except Exception as exc:  # noqa: BLE001
        loop_failed = True
        failure_error = exc
        traceback.print_exc()

        notifier.send(
            "NSE Quant paper loop FAILED\n"
            f"Run ID: {run_id}\n"
            f"Symbol: {primary_symbol}\n"
            f"Error type: {type(exc).__name__}\n"
            f"Error: {exc}",
        )

    finally:
        end_status = "failed" if loop_failed and failure_error is not None else "completed"

        notifier.send(
            f"NSE Quant paper loop {end_status}\n"
            f"Run ID: {run_id}\n"
            f"Symbol: {primary_symbol}\n"
            f"Ended at: {datetime.now(UTC).isoformat()}",
        )

        store.conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
