from datetime import UTC, datetime, timedelta

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.execution.broker import PaperBroker
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.strategy.decision_loop import DecisionLoop


class SyntheticProvider:
    def get_chain_snapshot(self):
        expiry = datetime.now(UTC).date() + timedelta(days=5)
        spot = 25000.0

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
            spot=spot,
            expiry=expiry,
            quotes=quotes,
        )


def test_decision_loop_persists_feature_and_decision(tmp_path):
    store = DuckDBStore(tmp_path / "loop.duckdb")
    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=PaperBroker(),
        run_id="test-run",
    )
    try:
        result = loop.run_once()
        assert result["status"] in {"no_proposal", "risk_rejected", "dry_run"}

        feature_count = store.conn.execute(
            "SELECT COUNT(*) FROM feature_snapshots"
        ).fetchone()[0]

        decision_count = store.conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]

        assert feature_count == 1
        assert decision_count >= 1
    finally:
        store.close()