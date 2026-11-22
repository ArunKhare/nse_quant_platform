"""Strategy-specific multi-timeframe timing filters.

A timing filter is strategy-specific decision evidence. It is not a market
regime and must not alter the canonical four-component institutional regime
label.

Initial mode is observation. Promotion to risk_sizing or hard_gate requires
explicit configuration and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nse_quant.core.evidence import EvidenceMode


class TimingFilterStatus(StrEnum):
    PASS = "PASS"
    OBSERVE = "OBSERVE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TimingFilterResult:
    filter_name: str
    filter_version: str
    mode: EvidenceMode
    status: TimingFilterStatus
    alignment: str | None
    size_multiplier: float
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is not TimingFilterStatus.BLOCK


class MultiTimeframeTimingFilter:
    """Evaluate multi-timeframe trend alignment for one strategy.

    This filter never changes the institutional regime label. In observation
    mode it records context only. In risk_sizing mode it may reduce size. In
    hard_gate mode it may block a new entry.
    """

    NAME = "multi_timeframe_timing"
    VERSION = "multi_timeframe_timing_v1"

    def __init__(
        self,
        *,
        mode: EvidenceMode = EvidenceMode.OBSERVATION,
        min_trend_strength: float = 0.0005,
        required_timeframes: tuple[str, ...] = ("15m", "60m"),
    ) -> None:
        if min_trend_strength < 0:
            raise ValueError("min_trend_strength must be non-negative")
        if not required_timeframes:
            raise ValueError("required_timeframes must not be empty")

        self.mode = mode
        self.min_trend_strength = min_trend_strength
        self.required_timeframes = tuple(required_timeframes)

    def evaluate(self, evidence: dict[str, Any] | None) -> TimingFilterResult:
        reasons: list[str] = []
        details: dict[str, Any] = {
            "required_timeframes": list(self.required_timeframes),
            "min_trend_strength": self.min_trend_strength,
        }

        if not evidence or not evidence.get("available"):
            return self._result(
                status=TimingFilterStatus.OBSERVE,
                alignment=None,
                reasons=["multi_timeframe_evidence_unavailable"],
                details=details,
            )

        if not evidence.get("complete"):
            reasons.append("multi_timeframe_evidence_incomplete")
            return self._result(
                status=TimingFilterStatus.OBSERVE,
                alignment=evidence.get("alignment"),
                reasons=reasons,
                details=details,
            )

        alignment = evidence.get("alignment")
        details["alignment"] = alignment

        timeframe_results = evidence.get("timeframes", {})
        directional: dict[str, bool] = {}
        trend_directions: list[str] = []

        for timeframe in self.required_timeframes:
            result = timeframe_results.get(timeframe, {})
            trend = result.get("trend")
            change = result.get("change")

            if trend is None:
                directional[timeframe] = False
                reasons.append(f"{timeframe}_trend_unavailable")
                continue

            if change is None:
                directional[timeframe] = False
                reasons.append(f"{timeframe}_trend_strength_unavailable")
                continue

            is_directional = abs(float(change)) >= self.min_trend_strength
            directional[timeframe] = is_directional

            if is_directional:
                trend_directions.append(str(trend).upper())

        details["directional_timeframes"] = directional

        if len(trend_directions) < len(self.required_timeframes):
            status = TimingFilterStatus.OBSERVE
            reasons.append("insufficient_directional_trend_context")
        elif len(set(trend_directions)) > 1:
            status = TimingFilterStatus.BLOCK
            reasons.append("multi_timeframe_trend_misaligned")
        else:
            status = TimingFilterStatus.PASS
            reasons.append("multi_timeframe_trend_aligned")

        return self._result(
            status=status,
            alignment=alignment,
            reasons=reasons,
            details=details,
        )

    def _result(
        self,
        *,
        status: TimingFilterStatus,
        alignment: str | None,
        reasons: list[str],
        details: dict[str, Any],
    ) -> TimingFilterResult:
        if self.mode is EvidenceMode.OBSERVATION:
            final_status = TimingFilterStatus.OBSERVE
            size_multiplier = 1.0
        elif self.mode is EvidenceMode.RISK_SIZING:
            final_status = TimingFilterStatus.OBSERVE if status is TimingFilterStatus.BLOCK else status
            size_multiplier = 0.0 if status is TimingFilterStatus.BLOCK else 1.0
        else:
            final_status = status
            size_multiplier = 0.0 if status is TimingFilterStatus.BLOCK else 1.0

        return TimingFilterResult(
            filter_name=self.NAME,
            filter_version=self.VERSION,
            mode=self.mode,
            status=final_status,
            alignment=alignment,
            size_multiplier=size_multiplier,
            reasons=reasons,
            details=details,
        )
