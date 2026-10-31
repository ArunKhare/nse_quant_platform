"""Observational quote quality; never authorizes trading."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from statistics import mean, median
from typing import Any

from nse_quant.core.models import ChainSnapshot, OptionQuote
from nse_quant.core.settings import ExecutionQualitySettings
from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)


class ExecutionQualityPlugin(EvidencePlugin):
    name = "execution_quality"

    def __init__(
        self,
        *,
        settings: ExecutionQualitySettings,
    ) -> None:
        self._settings = settings

    def build(self, context: DecisionContext) -> dict[str, Any]:
        as_of = self._utc(context.ts)
        snapshot: ChainSnapshot | None = context.snapshot

        base: dict[str, Any] = {
            "available": False,
            "complete": False,
            "as_of": as_of.isoformat(),
            "symbol": context.symbol,
            "classifier_version": "snapshot_quote_quality_v1",
            "max_quote_age_seconds": (self._settings.max_quote_age_seconds),
        }

        if snapshot is None:
            return {**base, "reason": "missing_snapshot"}

        snapshot_ts = self._utc(snapshot.ts)
        base.update(
            snapshot_ts=snapshot_ts.isoformat(),
            expiry=snapshot.expiry.isoformat(),
        )

        if snapshot_ts > as_of:
            return {**base, "reason": "future_snapshot"}

        if snapshot.underlying != context.symbol:
            return {**base, "reason": "snapshot_symbol_mismatch"}

        quotes = [quote for quote in snapshot.quotes if quote.instrument.expiry == snapshot.expiry]

        if not quotes:
            return {
                **base,
                "reason": "no_selected_expiry_quotes",
                "total_quotes": 0,
                "contracts": [],
            }

        tokens = [quote.instrument_token for quote in quotes]

        if len(tokens) != len(set(tokens)):
            return {**base, "reason": "duplicate_instrument_tokens"}

        if any(
            quote.instrument.underlying != context.symbol
            or quote.instrument_token != quote.instrument.instrument_token
            for quote in quotes
        ):
            return {**base, "reason": "quote_identity_mismatch"}

        contracts = [self._quote_quality(quote, as_of=as_of) for quote in quotes]

        spreads = [
            float(contract["spread_fraction"]) for contract in contracts if contract["usable"]
        ]

        complete = all(contract["complete"] for contract in contracts)

        return {
            **base,
            "available": True,
            "complete": complete,
            "total_quotes": len(contracts),
            "valid_two_sided_quotes": sum(
                contract["price_reason"] is None for contract in contracts
            ),
            "usable_quotes": len(spreads),
            "usable_quote_fraction": len(spreads) / len(contracts),
            "spread_summary": {
                "sample_count": len(spreads),
                "mean_fraction": mean(spreads) if spreads else None,
                "median_fraction": median(spreads) if spreads else None,
                "max_fraction": max(spreads) if spreads else None,
            },
            "exchange_timestamp_counts": self._timestamp_counts(
                contracts,
                field="exchange",
            ),
            "receipt_timestamp_counts": self._timestamp_counts(
                contracts,
                field="receipt",
            ),
            "trade_timestamp_counts": self._timestamp_counts(
                contracts,
                field="trade",
            ),
            "oi_available_quotes": sum(contract["oi_available"] for contract in contracts),
            "volume_available_quotes": sum(contract["volume_available"] for contract in contracts),
            "contracts": contracts,
            "reason": None if complete else "incomplete_quote_quality",
        }

    def _quote_quality(
        self,
        quote: OptionQuote,
        *,
        as_of: datetime,
    ) -> dict[str, Any]:
        price_reason = self._price_reason(quote.bid, quote.ask)

        spread_absolute: float | None = None
        spread_fraction: float | None = None

        if price_reason is None and quote.bid is not None and quote.ask is not None:
            spread_absolute = quote.ask - quote.bid
            midpoint = quote.bid / 2 + quote.ask / 2
            spread_fraction = spread_absolute / midpoint

        exchange = self._timestamp(quote.exchange_ts, as_of=as_of)
        receipt = self._timestamp(quote.received_at, as_of=as_of)
        trade = self._timestamp(quote.trade_ts, as_of=as_of)

        oi_available = quote.oi is not None and quote.oi >= 0
        volume_available = quote.volume is not None and quote.volume >= 0

        reasons = []

        if price_reason is not None:
            reasons.append(price_reason)

        for name, timestamp in (
            ("exchange", exchange),
            ("receipt", receipt),
        ):
            if timestamp["status"] != "fresh":
                reasons.append(f"{name}_{timestamp['status']}")

        # Trade time is not a substitute for quote freshness.
        # A missing or old last trade does not invalidate fresh BBO.
        if trade["status"] in {"future", "invalid"}:
            reasons.append(f"trade_{trade['status']}")

        usable = not reasons

        if not oi_available:
            reasons.append("missing_or_invalid_oi")

        if not volume_available:
            reasons.append("missing_or_invalid_volume")

        return {
            "instrument_token": quote.instrument_token,
            "tradingsymbol": quote.instrument.tradingsymbol,
            "option_type": quote.instrument.option_type.value,
            "price_reason": price_reason,
            "spread_absolute": spread_absolute,
            "spread_fraction": spread_fraction,
            "exchange": exchange,
            "receipt": receipt,
            "trade": trade,
            "oi": quote.oi,
            "volume": quote.volume,
            "oi_available": oi_available,
            "volume_available": volume_available,
            "usable": usable,
            "complete": not reasons,
            "reasons": reasons,
        }

    def _timestamp(
        self,
        value: datetime | None,
        *,
        as_of: datetime,
    ) -> dict[str, Any]:
        if value is None:
            return {
                "ts": None,
                "age_seconds": None,
                "status": "missing",
            }

        if value.tzinfo is None or value.utcoffset() is None:
            return {
                "ts": value.isoformat(),
                "age_seconds": None,
                "status": "invalid",
            }

        timestamp = value.astimezone(UTC)
        age = (as_of - timestamp).total_seconds()

        if age < 0:
            status = "future"
        elif age > self._settings.max_quote_age_seconds:
            status = "stale"
        else:
            status = "fresh"

        return {
            "ts": timestamp.isoformat(),
            "age_seconds": age,
            "status": status,
        }

    @staticmethod
    def _price_reason(
        bid: float | None,
        ask: float | None,
    ) -> str | None:
        if bid is None or ask is None:
            return "missing_bid_ask"

        if not math.isfinite(bid) or not math.isfinite(ask):
            return "non_finite_bid_ask"

        if bid <= 0 or ask <= 0:
            return "non_positive_bid_ask"

        if ask < bid:
            return "crossed_bid_ask"

        return None

    @staticmethod
    def _timestamp_counts(
        contracts: list[dict[str, Any]],
        *,
        field: str,
    ) -> dict[str, int]:
        return {
            status: sum(contract[field]["status"] == status for contract in contracts)
            for status in (
                "fresh",
                "stale",
                "future",
                "missing",
                "invalid",
            )
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Execution quality requires timezone-aware timestamps")

        return value.astimezone(UTC)
