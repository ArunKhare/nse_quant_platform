from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    Instrument,
    Leg,
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
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.strategy.decision_loop import DecisionLoop


@pytest.fixture
def test_settings():
    settings = Settings.model_validate(get_settings().model_dump())
    settings.safety.dry_run = False
    settings.safety.trading_enabled = True
    settings.safety.paper_trading = True
    settings.risk.max_open_positions = 1
    settings.runtime.allow_out_of_hours_testing = True
    return settings


@pytest.fixture
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

    return seed


@pytest.fixture
def test_store(tmp_path: Path):
    store = DuckDBStore(path=tmp_path / "test.duckdb")
    yield store
    store.close()


@pytest.fixture
def expiry() -> Any:
    return (datetime.now(UTC) + timedelta(days=3)).date()


@pytest.fixture
def instrument_factory(expiry):
    def build(
        strike: float,
        option_type: OptionType,
        token: int,
    ):
        suffix = "CE" if option_type == OptionType.CE else "PE"

        tradingsymbol = (
            f"NIFTY{expiry.strftime('%y%b').upper()}"
            f"{int(strike)}{suffix}"
        )

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

        return ChainSnapshot(
            underlying="NIFTY",
            ts=ts,
            spot=spot,
            expiry=expiry,
            quotes=[call, put],
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
            *,
            proposal: TradeProposal | None = None,
        ) -> Any:
            settings = get_settings()
            settings.research.enforce_feature_availability = False
            settings.research.enforce_regime_policy = False
            loop = DecisionLoop(
                store=test_store,
                provider=provider,
                broker=PaperBroker(),
                run_id="test-run",
                settings=test_settings,
                spot_instrument_token_resolver=lambda symbol: 256265,
                live_snapshot_path=live_snapshot_path,
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
        entry_limit_price=20.0,
        thesis="Test iron condor proposal",
        stop_loss_price=1000,
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
            )
            for option_type, side, token in [
                (OptionType.CE, OrderSide.BUY, 1001),
                (OptionType.PE, OrderSide.SELL, 1002),
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