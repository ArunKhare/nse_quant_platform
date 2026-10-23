"""Market-data quality assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DataQualityReport:
    is_usable: bool
    stale: bool
    missing_quotes: int
    missing_bid_ask: int
    zero_volume_legs: int
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DataQualityChecker:
    def __init__(self, stale_seconds: float, min_volume: int = 1) -> None:
        if stale_seconds <= 0:
            raise ValueError("stale_seconds must be positive")

        self.stale_seconds = stale_seconds
        self.min_volume = min_volume

    def assess(
        self,
        snapshot: Any,
        required_instrument_tokens: set[int] | None = None,
        now: datetime | None = None,
    ) -> DataQualityReport:
        now = now or datetime.now(UTC)
        issues: list[str] = []
        warnings: list[str] = []

        missing_quotes = 0
        missing_bid_ask = 0
        zero_volume_legs = 0

        for quote in snapshot.quotes:
            token = quote.instrument_token

            if required_instrument_tokens and token not in required_instrument_tokens:
                continue

            if quote.ltp is None and quote.bid is None and quote.ask is None:
                missing_quotes += 1
                issues.append(f"missing_quote:{token}")
                continue

            if quote.bid is None or quote.ask is None:
                missing_bid_ask += 1
                warnings.append(f"missing_bid_ask:{token}")

            if (quote.volume or 0) < self.min_volume:
                zero_volume_legs += 1
                warnings.append(f"low_volume:{token}")

            quote_time = quote.exchange_ts or quote.trade_ts or quote.received_at

            if quote_time.tzinfo is None:
                quote_time = quote_time.replace(tzinfo=UTC)

            age_seconds = (now - quote_time).total_seconds()

            if age_seconds > self.stale_seconds:
                issues.append(f"stale_quote:{token}:age={age_seconds:.0f}")

        return DataQualityReport(
            is_usable=not issues,
            stale=bool(issues),
            missing_quotes=missing_quotes,
            missing_bid_ask=missing_bid_ask,
            zero_volume_legs=zero_volume_legs,
            issues=issues,
            warnings=warnings,
        )
