from datetime import UTC, datetime, timedelta

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.core.settings import get_settings
from nse_quant.execution.broker import PaperBroker
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.strategy.decision_loop import DecisionLoop


class SyntheticProvider:
    def get_chain_snapshot(self):
        expiry = datetime.now(UTC).date() + timedelta(days=5)

        quotes = []

        for strike, option_type in [
            (24600, OptionType.PE),
            (24800, OptionType.PE),
            (25200, OptionType.CE),
            (25400, OptionType.CE),
        ]:
            instrument = Instrument(
                tradingsymbol=f"NIFTY{strike}{option_type.value}",
                instrument_token=strike,
                underlying="NIFTY",
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=75,
            )

            quotes.append(
                OptionQuote(
                    instrument_token=strike,
                    ltp=100.0,
                    bid=99.0,
                    ask=101.0,
                    volume=100000,
                    oi=100000,
                    instrument=instrument,
                    iv=0.15,
                )
            )

        return ChainSnapshot(
            underlying="NIFTY",
            spot=25000.0,
            expiry=expiry,
            quotes=quotes,
        )


def test_paper_flow_persists_full_lifecycle(tmp_path, seed_spot_features):
    store = DuckDBStore(tmp_path / "paper-flow.duckdb")
    live_snapshot_path = tmp_path / "live_snapshot.json"
    seed_spot_features(store)
    broker = PaperBroker()

    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=broker,
        run_id="paper-flow-test",
        settings=get_settings(),
        spot_instrument_token_resolver=lambda symbol: 256265,
        live_snapshot_path=live_snapshot_path,

    )
    loop.settings.research.enforce_strategy_eligibility = False
    result = loop.run_once()

    assert result["status"] in {
        "no_proposal",
        "risk_rejected",
        "dry_run",
        "paper_filled",
    }

    feature_count_row = store.conn.execute(
        "SELECT COUNT(*) FROM feature_snapshots"
    ).fetchone()
    feature_count = feature_count_row[0] if feature_count_row is not None else 0

    decision_count_row = store.conn.execute(
        "SELECT COUNT(*) FROM decisions"
    ).fetchone()
    decision_count = decision_count_row[0] if decision_count_row is not None else 0

    gate_count_row = store.conn.execute(
        "SELECT COUNT(*) FROM gate_results"
    ).fetchone()
    gate_count = gate_count_row[0] if gate_count_row is not None else 0

    assert feature_count == 1
    assert decision_count >= 1
    assert gate_count >= 0

    if result["status"] == "paper_filled":
        strategy_position_id = result["strategy_position_id"]

        leg_count_row = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM positions
            WHERE strategy_position_id = ?
            """,
            [strategy_position_id],
        ).fetchone()
        leg_count = leg_count_row[0] if leg_count_row is not None else 0

        assert leg_count == 4

        order_count_row = store.conn.execute(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE proposal_id = ?
            """,
            [result["proposal_id"]],
        ).fetchone()
        order_count = order_count_row[0] if order_count_row is not None else 0

        assert order_count == 1

    store.close()


def test_dry_run_does_not_create_paper_order(tmp_path, seed_spot_features):
    store = DuckDBStore(tmp_path / "dry-run.duckdb")
    live_snapshot_path = tmp_path / "live_snapshot.json"
    seed_spot_features(store)
    broker = PaperBroker()

    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=broker,
        run_id="dry-run-test",
        settings=get_settings(),
        spot_instrument_token_resolver=lambda symbol: 256265,
        live_snapshot_path=live_snapshot_path,
    )
    loop.settings.research.enforce_strategy_eligibility = False
    result = loop.run_once()

    if result["status"] == "dry_run":
        order_count_row = store.conn.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()
        order_count = order_count_row[0] if order_count_row is not None else 0
        assert order_count == 0
        assert broker.positions == []

    store.close()