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
        quotes = []

        for strike, option_type, ltp, bid, ask in [
            (24600, OptionType.PE, 100.0, 99.0, 101.0),
            (24800, OptionType.PE, 80.0, 79.0, 81.0),
            (25200, OptionType.CE, 80.0, 79.0, 81.0),
            (25400, OptionType.CE, 100.0, 99.0, 101.0),
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
                    ltp=ltp,
                    bid=bid,
                    ask=ask,
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


def test_mid_price_is_used_when_bid_and_ask_are_valid(tmp_path):
    store = DuckDBStore(tmp_path / "marking.duckdb")
    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=PaperBroker(),
        run_id="marking-test",
        spot_instrument_token_resolver=lambda symbol: 256265,
    )

    snapshot = loop.provider.get_chain_snapshot()
    quote = snapshot.quotes[0]

    assert loop._mark_price(quote) == 100.0

    store.close()


def test_ltp_fallback_when_quotes_invalid(tmp_path):
    store = DuckDBStore(tmp_path / "marking.duckdb")
    loop = DecisionLoop(
        store=store,
        provider=SyntheticProvider(),
        broker=PaperBroker(),
        run_id="marking-test",
        spot_instrument_token_resolver=lambda symbol: 256265,
    )

    snapshot = loop.provider.get_chain_snapshot()
    quote = snapshot.quotes[0].model_copy(update={"bid": None, "ask": None})

    assert loop._mark_price(quote) == quote.ltp

    store.close()