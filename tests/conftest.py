from __future__ import annotations

import gc
import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    Instrument,
    Leg,
    MarketFeatures,
    OptionQuote,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.core.settings import Settings, get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.market_data.replay_provider import (
    ReplayMarketDataProvider,
)
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.regime_risk_policy import RegimeRiskLimits
from nse_quant.strategy.decision_loop import DecisionLoop
from tests.data_platform.native_failure_acceptance_lab import NativeFailureLab


def pytest_configure(config):
    """Give each terminal run its own timestamped folder and per-worker log files."""
    if config.getoption("s2_evidence_output", default=None) is not None:
        return
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    if worker_id == "master":
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        os.environ["PYTEST_RUN_ID"] = run_id
    else:
        run_id = os.environ.get("PYTEST_RUN_ID", f"run_fallback_{os.getppid()}")

    run_dir = Path("test_results") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    config.option.log_file = str(run_dir / f"pytest_{worker_id}.log")

    if getattr(config.option, "xmlpath", None):
        config.option.xmlpath = str(run_dir / "junit.xml")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Log exact START and END markers for every test in the worker log file."""
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    logging.info(f"[{worker_id}] START: {item.nodeid}")
    yield
    logging.info(f"[{worker_id}] END:   {item.nodeid}")


@pytest.fixture(scope="session", autouse=True)
def cap_duckdb_resources():
    """Bound DuckDB memory and threads for 4 workers on a 15.2 GB / 12-core machine."""
    original_connect = duckdb.connect

    def bounded_connect(*args, **kwargs):
        config = dict(kwargs.get("config") or {})
        config.setdefault("memory_limit", "2500MB")
        config.setdefault("threads", 2)
        kwargs["config"] = config
        return original_connect(*args, **kwargs)

    duckdb.connect = bounded_connect
    yield
    duckdb.connect = original_connect


@contextmanager
def _seed_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            os.mkdir(lock_path)
            break
        except FileExistsError:
            time.sleep(0.2)
    try:
        yield
    finally:
        shutil.rmtree(lock_path, ignore_errors=True)


@pytest.fixture(scope="session")
def _seed_native_failure_lab(tmp_path_factory):
    """Build NativeFailureLab ONCE per worker (serialized across workers) and snapshot."""
    work_root = tmp_path_factory.mktemp("native_failure_lab_work")
    backup_root = tmp_path_factory.mktemp("native_failure_lab_backup")
    lock_path = tmp_path_factory.getbasetemp().parent / "native_failure_lab_seed.lock"

    with _seed_lock(lock_path):
        lab_instance = NativeFailureLab(work_root)

    shutil.copytree(work_root, backup_root, dirs_exist_ok=True)
    return work_root, backup_root, lab_instance


@pytest.fixture
def lab(_seed_native_failure_lab):
    work_root, backup_root, lab_instance = _seed_native_failure_lab
    shutil.rmtree(work_root)
    subprocess.run(
        ["cp", "-a", "--reflink=auto", str(backup_root), str(work_root)],
        check=True,
    )
    return lab_instance


@pytest.fixture(autouse=True)
def cleanup_memory_after_test():
    """Release pandas DataFrames and DuckDB buffers immediately after each test."""
    yield
    gc.collect()


@pytest.fixture(scope="session")
def test_settings():
    settings = Settings.model_validate(get_settings().model_dump())
    settings.safety.dry_run = False
    settings.safety.trading_enabled = True
    settings.safety.paper_trading = True
    settings.risk.max_open_positions = 1
    settings.runtime.allow_out_of_hours_testing = True
    return settings


@pytest.fixture(scope="session")
def _seed_candles():
    def seed(
        store: DuckDBStore,
        token: int,
        symbol: str,
        count: int,
        interval: str,
    ) -> None:
        base_ts = datetime.now(UTC) - timedelta(minutes=count + 1)
        candles = [
            {
                "date": base_ts + timedelta(minutes=i),
                "open": 23000.0,
                "high": 23010.0,
                "low": 22990.0,
                "close": 23000.0,
                "volume": 1000,
                "oi": 0,
            }
            for i in range(count)
        ]

        store.write_spot_candles(
            candles=candles,
            symbol=symbol,
            instrument_token=token,
            interval=interval,
        )

    return seed


@pytest.fixture(scope="session")
def seed_spot_features():
    def seed(store: DuckDBStore, symbol: str = "NIFTY") -> None:
        now = datetime.now(UTC)
        store.write_spot_features(
            pd.DataFrame(
                [
                    {
                        "symbol": symbol,
                        "ts": now,
                        "close": 23000.0,
                        "return_1m": 0.001,
                        "rv_1m_30": 0.2,
                        "atr_1m_14": 10.0,
                        "vwap_1m": 23000.0,
                        "vwap_distance_1m": 0.0,
                        "volume_zscore_1m_30": 0.5,
                        "trend_15m": 0.01,
                        "atr_15m_14": 20.0,
                        "range_position_15m": 0.5,
                        "trend_60m": 0.02,
                        "atr_60m_14": 30.0,
                        "range_position_60m": 0.5,
                    }
                ]
            )
        )
        seed_daily_candles(store, symbol=symbol)

    return seed


SPOT_TOKEN = 256265


def seed_daily_candles(
    store: DuckDBStore,
    symbol: str = "NIFTY",
    *,
    days: int = 30,
    daily_move: float = 0.003,
    instrument_token: int = SPOT_TOKEN,
) -> None:
    """Seed completed daily candles before today (IST) for the VRP RV input.

    Alternating +/- ``daily_move`` closes give a trailing annualized RV of
    roughly daily_move * sqrt(252) (about 0.05 by default), well below the
    fixtures' ATM IV, so the mandatory VRP gate passes in happy-path tests.
    """
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    today = datetime.now(ist).date()
    close = 23000.0
    candles = []
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        close *= 1 + (daily_move if offset % 2 else -daily_move)
        candles.append(
            {
                "date": datetime(day.year, day.month, day.day, tzinfo=ist),
                "open": close,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 0,
            }
        )
    store.write_spot_candles(candles, symbol=symbol, instrument_token=instrument_token, interval="day")


@pytest.fixture(scope="session")
def _template_duckdb(tmp_path_factory) -> Path:
    """Create and initialize the DuckDB schema once per xdist worker."""
    template_path = tmp_path_factory.mktemp("db_template") / "template.duckdb"
    store = DuckDBStore(path=template_path)
    store.close()
    return template_path


@pytest.fixture
def test_store(_template_duckdb: Path, tmp_path: Path):
    """Clone the pre-initialized DB file for each test to skip DDL overhead."""
    db_path = tmp_path / "test.duckdb"
    shutil.copy2(_template_duckdb, db_path)
    store = DuckDBStore(path=db_path)
    yield store
    store.close()


@pytest.fixture(scope="session")
def expiry() -> Any:
    return (datetime.now(UTC) + timedelta(days=3)).date()


@pytest.fixture
def decisioncontext_factory(snapshot_factory):
    def build(
        *,
        run_id: str = "runid",
        symbol: str = "NIFTY",
        ts: datetime | None = None,
        current_iv: float | None = 0.18,
        features: MarketFeatures | None = None,
        snapshot: ChainSnapshot | None = None,
        iv_history_count: int = 0,
        current_regime: str | None = None,
        effective_regimes: list[str] | None = None,
        regime_policy: dict[str, Any] | None = None,
        spot_instrument_token: int = 256265,
    ) -> DecisionContext:
        context_ts = ts or datetime.now(UTC)
        context_snapshot = snapshot or snapshot_factory(
            spot=23_000.0,
            call_price=100.0,
            put_price=100.0,
            ts=context_ts,
        )
        context_features = features or MarketFeatures(
            ts=context_ts,
            underlying=symbol,
            spot=context_snapshot.spot,
            expiry=context_snapshot.expiry,
            atm_iv=current_iv,
        )

        return DecisionContext(
            run_id=run_id,
            symbol=symbol,
            ts=context_ts,
            features=context_features,
            snapshot=context_snapshot,
            iv_history_count=iv_history_count,
            current_regime=current_regime,
            effective_regimes=effective_regimes or [],
            regime_policy=regime_policy,
            spot_instrument_token=spot_instrument_token,
        )

    return build


@pytest.fixture
def instrument_factory(expiry):
    def build(
        strike: float,
        option_type: OptionType,
        token: int,
    ):
        suffix = "CE" if option_type == OptionType.CE else "PE"

        tradingsymbol = f"NIFTY{expiry.strftime('%y%b').upper()}{int(strike)}{suffix}"

        return Instrument(
            tradingsymbol=tradingsymbol,
            instrument_token=token,
            underlying="NIFTY",
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            lot_size=65,
        )

    return build


@pytest.fixture
def snapshot_factory(expiry, instrument_factory):
    def build(
        spot: float,
        call_price: float,
        put_price: float,
        ts: datetime | None = None,
    ) -> ChainSnapshot:
        ts = ts or datetime.now(UTC)

        call_instrument = instrument_factory(
            strike=23000,
            option_type=OptionType.CE,
            token=1001,
        )

        put_instrument = instrument_factory(
            strike=23000,
            option_type=OptionType.PE,
            token=1002,
        )

        call = OptionQuote(
            instrument_token=1001,
            instrument=call_instrument,
            ltp=call_price,
            bid=call_price - 0.5,
            ask=call_price + 0.5,
            volume=1000,
            oi=100000,
            received_at=ts,
        )

        put = OptionQuote(
            instrument_token=1002,
            instrument=put_instrument,
            ltp=put_price,
            bid=put_price - 0.5,
            ask=put_price + 0.5,
            volume=1000,
            oi=100000,
            received_at=ts,
        )

        # The decision loop requires settings.analytics.expiries_per_snapshot
        # distinct expiries (2 in settings.test.yaml). Add a next-week expiry so
        # replay snapshots satisfy the completeness gate without weakening it.
        next_expiry = expiry + timedelta(days=7)
        next_quotes = []
        for token, option_type, price in (
            (2001, OptionType.CE, call_price * 1.4),
            (2002, OptionType.PE, put_price * 1.4),
        ):
            suffix = "CE" if option_type == OptionType.CE else "PE"
            next_quotes.append(
                OptionQuote(
                    instrument_token=token,
                    instrument=Instrument(
                        tradingsymbol=f"NIFTY{next_expiry.strftime('%y%b').upper()}23000{suffix}NX",
                        instrument_token=token,
                        underlying="NIFTY",
                        expiry=next_expiry,
                        strike=23000,
                        option_type=option_type,
                        lot_size=65,
                    ),
                    ltp=price,
                    bid=price - 0.5,
                    ask=price + 0.5,
                    volume=1000,
                    oi=100000,
                    received_at=ts,
                )
            )

        return ChainSnapshot(
            underlying="NIFTY",
            ts=ts,
            spot=spot,
            expiry=expiry,
            quotes=[call, put, *next_quotes],
        )

    return build


@pytest.fixture
def decision_loop_environment(
    test_settings,
    test_store,
    monkeypatch,
    seed_spot_features,
    tmp_path,
):
    seed_spot_features(test_store)
    live_snapshot_path = tmp_path / "live_snapshot.json"

    class Environment:
        def build_loop(
            self,
            provider: ReplayMarketDataProvider,
            proposal: TradeProposal | None = None,
            *,
            enforce_strategy_eligibility: bool = False,
            approve_regime_risk: bool = False,
        ) -> Any:
            loop = DecisionLoop(
                store=test_store,
                provider=provider,
                broker=PaperBroker(),
                run_id="test-run",
                settings=test_settings,
                spot_instrument_token_resolver=lambda symbol: 256265,
                live_snapshot_path=live_snapshot_path,
                kill_switch=KillSwitch(tmp_path / "kill_switch.json"),
            )
            loop.settings.research.enforce_feature_availability = False
            loop.settings.research.enforce_regime_policy = False
            loop.settings.research.enforce_strategy_eligibility = enforce_strategy_eligibility

            if approve_regime_risk:
                test_regime_limits = RegimeRiskLimits(
                    regime="UNKNOWN",
                    allowed=True,
                    max_lots_per_order=100,
                    max_open_positions=100,
                    max_notional_exposure=1_000_000_000.0,
                    max_portfolio_vega=1_000_000_000.0,
                    max_daily_loss=1_000_000_000.0,
                    reason="TEST_APPROVED",
                )

                monkeypatch.setattr(
                    loop,
                    "_apply_regime_limits",
                    lambda *args, **kwargs: test_regime_limits,
                )

            if proposal is not None:
                gates = self._build_gates()

                monkeypatch.setattr(
                    loop.strategy,
                    "evaluate",
                    lambda *args, **kwargs: (proposal, gates),
                )

            return loop

        @staticmethod
        def _build_gates() -> list[Any]:
            return [
                GateResult(
                    gate="test_gate",
                    passed=True,
                    reason="Test gate passed",
                )
            ]

    return Environment()


@pytest.fixture
def decision_loop(
    decision_loop_environment,
    snapshot_factory,
):
    provider = ReplayMarketDataProvider(
        [
            snapshot_factory(
                spot=23000.0,
                call_price=120.0,
                put_price=115.0,
            )
        ]
    )
    return decision_loop_environment.build_loop(provider)


@pytest.fixture
def test_proposal(expiry, instrument_factory) -> TradeProposal:
    return TradeProposal(
        proposal_id="test-proposal",
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=expiry,
        entry_limit_price=1300.0,
        thesis="Test iron condor proposal",
        stop_loss_price=500,
        metadata={},
        legs=[
            Leg(
                instrument=instrument_factory(
                    23000,
                    option_type,
                    token,
                ),
                side=side,
                lots=1,
                entry_price=entry_price,
            )
            for option_type, side, token, entry_price in [
                (OptionType.CE, OrderSide.BUY, 1001, 100.0),
                (OptionType.PE, OrderSide.SELL, 1050, 120.0),
            ]
        ],
    )


@pytest.fixture
def replay_snapshots(snapshot_factory, test_proposal):
    return {
        "proposal": test_proposal,
        "snapshots": [
            snapshot_factory(
                spot=23000.0,
                call_price=120.0,
                put_price=115.0,
            ),
            snapshot_factory(
                spot=23010.0,
                call_price=118.0,
                put_price=117.0,
            ),
        ],
    }


@pytest.fixture
def exit_trigger_snapshots(snapshot_factory, test_proposal):
    return {
        "proposal": test_proposal,
        "snapshots": [
            snapshot_factory(
                spot=23000.0,
                call_price=120.0,
                put_price=115.0,
            ),
            snapshot_factory(
                spot=22500.0,
                call_price=280.0,
                put_price=20.0,
            ),
        ],
    }


@pytest.fixture
def entry_snapshots(snapshot_factory, test_proposal):
    return {
        "proposal": test_proposal,
        "snapshots": [
            snapshot_factory(
                spot=23000.0,
                call_price=120.0,
                put_price=115.0,
            ),
            snapshot_factory(
                spot=23000.0,
                call_price=120.0,
                put_price=115.0,
            ),
        ],
    }


@pytest.fixture
def backtest_proposal(expiry, instrument_factory) -> TradeProposal:
    return TradeProposal(
        proposal_id="backtest-proposal",
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        expiry=expiry,
        thesis="Backtest proposal",
        legs=[
            Leg(
                instrument=instrument_factory(23000, OptionType.CE, 1001),
                side=OrderSide.BUY,
                lots=1,
                entry_price=100.0,
            ),
            Leg(
                instrument=instrument_factory(23000, OptionType.PE, 1002),
                side=OrderSide.SELL,
                lots=1,
                entry_price=120.0,
            ),
        ],
        entry_limit_price=20.0,
        target_price=10.0,
        stop_loss_price=40.0,
        metadata={"net_credit": 20.0},
    )
