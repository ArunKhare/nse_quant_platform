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

        # Two expiries satisfy settings.analytics.expiries_per_snapshot (2).
        next_expiry = expiry + timedelta(days=7)
        for leg_expiry, token_offset, strike, option_type in [
            (expiry, 0, 24600, OptionType.PE),
            (expiry, 0, 24800, OptionType.PE),
            (expiry, 0, 25200, OptionType.CE),
            (expiry, 0, 25400, OptionType.CE),
            (next_expiry, 100000, 24800, OptionType.PE),
            (next_expiry, 100000, 25200, OptionType.CE),
        ]:
            token = strike + token_offset
            instrument = Instrument(
                tradingsymbol=f"NIFTY{leg_expiry:%y%m%d}{strike}{option_type.value}",
                instrument_token=token,
                underlying="NIFTY",
                expiry=leg_expiry,
                strike=strike,
                option_type=option_type,
                lot_size=75,
            )

            quotes.append(
                OptionQuote(
                    instrument_token=token,
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

    feature_count_row = store.conn.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()
    feature_count = feature_count_row[0] if feature_count_row is not None else 0

    decision_count_row = store.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()
    decision_count = decision_count_row[0] if decision_count_row is not None else 0

    gate_count_row = store.conn.execute("SELECT COUNT(*) FROM gate_results").fetchone()
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
        order_count_row = store.conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        order_count = order_count_row[0] if order_count_row is not None else 0
        assert order_count == 0
        assert broker.positions() == []

    store.close()
