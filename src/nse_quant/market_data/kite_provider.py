"""Kite REST provider."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from nse_quant.core.models import ChainSnapshot, Instrument, OptionType
from nse_quant.core.settings import get_settings
from nse_quant.market_data import chain


class InstrumentResolutionError(ValueError):
    """Raised when an underlying cannot be resolved to a Kite instrument."""

class KiteMarketDataProvider:
    def __init__(self, kite:Any, underlying:str|None=None):
        self.settings = get_settings()
        self.kite=kite
        self.underlying=underlying or self.settings.universe.underlying
        self._instruments:list[dict[str, Any]] | None = None
        # self._index_instruments: list[dict[str, Any]] | None = None
        self._instrument_cache: dict[str, list[dict[str, Any]]] = {}

    def _is_index(self, symbol: str) -> bool:
        if self.settings is None:
            return symbol in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
        return symbol in set(self.settings.market_data.index_symbols)

    def _load_nse_instruments(self) -> list[dict[str, Any]]:
        if "NSE" not in self._instrument_cache:
            self._instrument_cache["NSE"] = self.kite.instruments("NSE")
        return self._instrument_cache["NSE"]

    def _load_nfo_instruments(self) -> list[dict[str, Any]]:
        if self._instruments is None:
            self.refresh_instruments()

        assert self._instruments is not None
        return self._instruments

    def _resolve_index_token(self, symbol: str) -> int:
        market_data = self.settings.market_data

        override = market_data.index_instrument_tokens.get(symbol)
        if override:
            return int(override)

        index_tradingsymbol = market_data.index_instrument_symbols.get(symbol)
        if not index_tradingsymbol:
            raise InstrumentResolutionError(
                f"No Kite index tradingsymbol configured for underlying {symbol!r}"
            )

        matches = [
            row
            for row in self._load_nse_instruments()
            if row.get("exchange") == "NSE"
            and row.get("segment") == "INDICES"
            and row.get("tradingsymbol") == index_tradingsymbol
        ]

        if len(matches) != 1:
            raise InstrumentResolutionError(
                f"Expected one NSE INDICES instrument for {symbol!r} "
                f"({index_tradingsymbol!r}), found {len(matches)}"
            )

        return int(matches[0]["instrument_token"])

    def _resolve_equity_token(self, symbol: str) -> int:
        matches = [
            row
            for row in self._load_nse_instruments()
            if row.get("exchange") == "NSE"
            and row.get("instrument_type") == "EQ"
            and row.get("segment") != "INDICES"
            and row.get("tradingsymbol") == symbol
        ]

        if len(matches) != 1:
            raise InstrumentResolutionError(
                f"Expected one NSE EQ instrument for {symbol!r}, "
                f"found {len(matches)}"
            )

        return int(matches[0]["instrument_token"])

    def resolve_spot_instrument_token(self, symbol: str) -> int:
        """Resolve an underlying to its NSE spot instrument token."""
        if self._is_index(symbol):
            return self._resolve_index_token(symbol)

        return self._resolve_equity_token(symbol)

    def refresh_instruments(self) -> None:
        """Load and cache NFO option instruments."""
        self._instruments = self.kite.instruments("NFO")

    def refresh_index_instruments(self) -> None:
        self._index_instruments = self.kite.instruments("NSE")

    def get_index_instrument_token(
        self,
        symbol: str,
    ) -> int:
        if self._index_instruments is None:
            self.refresh_index_instruments()

        assert self._index_instruments is not None

        index_symbol = (
            self.settings
            .market_data
            .index_instrument_symbols
            .get(symbol)
        )

        if index_symbol is None:
            raise ValueError(
                f"No index instrument mapping for {symbol}"
            )

        matches = [
            instrument
            for instrument in self._index_instruments
            if instrument["exchange"] == "NSE"
            and instrument["instrument_type"] == "INDEX"
            and instrument["tradingsymbol"] == index_symbol
        ]

        if not matches:
            raise ValueError(
                f"Index instrument not found: {index_symbol}"
            )

        return int(matches[0]["instrument_token"])
    def get_spot(self) -> float:
        key = self.get_spot_key(self.underlying)

        quote = self.kite.quote([key])[key]

        return float(quote["last_price"])
    def get_spot_key(self, symbol: str) -> str:
        configured = self.settings.market_data.spot_quote_keys.get(symbol)
        if configured:
            return configured

        if self._is_index(symbol):
            raise ValueError(
                f"No spot_quote_keys mapping configured for index {symbol!r}"
            )

        return f"NSE:{symbol}"

    def get_chain_snapshot(self, expiry: date | None = None):
        raw_instruments = self._load_nfo_instruments()

        candidate_instruments = [
            row
            for row in raw_instruments
            if row.get("instrument_type") in {"CE", "PE"}
            and row.get("name") == self.underlying
        ]

        spot = self.get_spot()

        expiry_date, option_instruments = chain.discover_chain(
            candidate_instruments,
            self.underlying,
            spot,
            expiry,
            self.settings.universe.strikes_per_side,
        )

        raw = self.kite.quote(
            [
                f"NFO:{instrument.tradingsymbol}"
                for instrument in option_instruments
            ]
        )

        ticks: dict[int, dict[str, Any]] = {}
        received_at = datetime.now(UTC)

        for instrument in option_instruments:
            quote = raw.get(
                f"NFO:{instrument.tradingsymbol}",
                {},
            )

            depth = quote.get("depth") or {}

            ticks[instrument.instrument_token] = {
                "ltp": quote.get("last_price"),
                "bid": (depth.get("buy") or [{}])[0].get("price"),
                "ask": (depth.get("sell") or [{}])[0].get("price"),
                "volume": quote.get("volume"),
                "oi": quote.get("oi"),
                "exchange_ts": quote.get("exchange_timestamp"),
                "trade_ts": quote.get("last_trade_time"),
                "received_at": received_at,
            }

        return chain.build_snapshot(
            self.underlying,
            spot,
            expiry_date,
            option_instruments,
            ticks,
        )

    def get_chain_snapshots(self) -> list[ChainSnapshot]:
        settings = self.settings

        expiry_count = (
            settings.analytics.expiries_per_snapshot
        )

        raw_instruments = self._load_nfo_instruments()

        candidate_instruments = [
            row
            for row in raw_instruments
            if row.get("instrument_type") in {"CE", "PE"}
            and row.get("name") == self.underlying
        ]

        spot = self.get_spot()

        chains = chain.discover_chain_multi_expiry(
            instruments=candidate_instruments,
            underlying=self.underlying,
            spot=spot,
            expiries_requested=expiry_count,
            strikes_per_side=(
                self.settings.universe.strikes_per_side
            ),
        )

        snapshot_ts = datetime.now(UTC)
        snapshots: list[ChainSnapshot] = []

        for expiry, option_instruments in chains:
            raw = self.kite.quote(
                [
                    f"NFO:{instrument.tradingsymbol}"
                    for instrument in option_instruments
                ]
            )

            ticks: dict[int, dict[str, Any]] = {}

            for instrument in option_instruments:
                quote = raw.get(
                    f"NFO:{instrument.tradingsymbol}",
                    {},
                )

                depth = quote.get("depth") or {}

                ticks[instrument.instrument_token] = {
                    "ltp": quote.get("last_price"),
                    "bid": (
                        depth.get("buy") or [{}]
                    )[0].get("price"),
                    "ask": (
                        depth.get("sell") or [{}]
                    )[0].get("price"),
                    "volume": quote.get("volume"),
                    "oi": quote.get("oi"),
                    "exchange_ts": quote.get(
                        "exchange_timestamp"
                    ),
                    "trade_ts": quote.get(
                        "last_trade_time"
                    ),
                    "received_at":  snapshot_ts,
                }

            snapshots.append(
                chain.build_snapshot(
                    self.underlying,
                    spot,
                    expiry,
                    option_instruments,
                    ticks,
                )
            )

        return snapshots

    def get_historical_candles(
            self,
            symbol: str,
            interval: str,
            from_dt: datetime,
            to_dt: datetime,
        ) -> list[dict[str, Any]]:
            """Fetch historical spot candles for an index or equity underlying."""
            kite_interval = self._resolve_kite_interval(interval)
            instrument_token = self.resolve_spot_instrument_token(symbol)

            raw: list[dict[str, Any]] = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=kite_interval,
            )

            for candle in raw:
                candle["symbol"] = symbol
                candle["interval"] = interval
                candle["instrument_token"] = instrument_token

            return raw

    def _resolve_kite_interval(self, interval: str) -> str:
        try:
            return self.settings.market_data.candle_intervals[
                interval
            ].kite_interval
        except KeyError as exc:
            raise ValueError(
                f"Unsupported candle interval: {interval!r}"
            ) from exc

    def _normalize_nfo_instrument(
        self,
        row: dict[str, Any],
    ) -> Instrument:
        option_type = OptionType(row["instrument_type"])

        expiry = row["expiry"]
        if isinstance(expiry, str):
            expiry = datetime.strptime(expiry, "%Y-%m-%d").date()
        elif not isinstance(expiry, date):
            expiry = pd.to_datetime(expiry).date()

        return Instrument(
            tradingsymbol=str(row["tradingsymbol"]),
            instrument_token=int(row["instrument_token"]),
            underlying=str(row["name"]),
            expiry=expiry,
            strike=float(row["strike"]),
            option_type=option_type,
            lot_size=int(row["lot_size"]),
        )