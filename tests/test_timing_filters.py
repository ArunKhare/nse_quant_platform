import pytest

from nse_quant.core.evidence import EvidenceMode
from nse_quant.strategy.timing_filters import (
    MultiTimeframeTimingFilter,
    TimingFilterStatus,
)


def _evidence(alignment: str, change_15m: float, change_60m: float) -> dict:
    return {
        "available": True,
        "complete": True,
        "alignment": alignment,
        "timeframes": {
            "15m": {"trend": "UP" if change_15m > 0 else "DOWN", "change": change_15m},
            "60m": {"trend": "UP" if change_60m > 0 else "DOWN", "change": change_60m},
        },
    }


def test_observation_mode_never_blocks() -> None:
    evidence = _evidence("MIXED", 0.01, -0.01)
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.OBSERVATION).evaluate(evidence)

    assert result.status is TimingFilterStatus.OBSERVE
    assert result.passed
    assert result.size_multiplier == 1.0
    assert "multi_timeframe_trend_misaligned" in result.reasons


def test_aligned_trend_passes_in_hard_gate_mode() -> None:
    evidence = _evidence("BULLISH", 0.01, 0.02)
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.HARD_GATE).evaluate(evidence)

    assert result.status is TimingFilterStatus.PASS
    assert result.passed
    assert result.size_multiplier == 1.0


def test_misaligned_trend_blocks_in_hard_gate_mode() -> None:
    evidence = _evidence("MIXED", 0.01, -0.01)
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.HARD_GATE).evaluate(evidence)

    assert result.status is TimingFilterStatus.BLOCK
    assert not result.passed
    assert result.size_multiplier == 0.0


def test_risk_sizing_mode_reduces_size_on_misalignment() -> None:
    evidence = _evidence("MIXED", 0.01, -0.01)
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.RISK_SIZING).evaluate(evidence)

    assert result.status is TimingFilterStatus.OBSERVE
    assert result.passed
    assert result.size_multiplier == 0.0


def test_weak_trend_is_observation_not_block() -> None:
    evidence = _evidence("BULLISH", 0.0001, 0.0001)
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.HARD_GATE).evaluate(evidence)

    assert result.status is TimingFilterStatus.OBSERVE
    assert result.passed
    assert "insufficient_directional_trend_context" in result.reasons


def test_missing_evidence_is_observation() -> None:
    result = MultiTimeframeTimingFilter(mode=EvidenceMode.HARD_GATE).evaluate(None)

    assert result.status is TimingFilterStatus.OBSERVE
    assert result.passed
    assert result.alignment is None



ALIGNED = _evidence("BULLISH", 0.01, 0.02)
MISALIGNED = _evidence("MIXED", 0.01, -0.01)
WEAK = _evidence("BULLISH", 0.0001, 0.0001)


@pytest.mark.parametrize(
    "mode,evidence,status,multiplier",
    [
        # Charter / Stage 1 item 8: mode-specific policy matrix.
        (EvidenceMode.OBSERVATION, MISALIGNED, TimingFilterStatus.OBSERVE, 1.0),
        (EvidenceMode.RISK_SIZING, MISALIGNED, TimingFilterStatus.OBSERVE, 0.0),
        (EvidenceMode.HARD_GATE, MISALIGNED, TimingFilterStatus.BLOCK, 0.0),
        (EvidenceMode.OBSERVATION, ALIGNED, TimingFilterStatus.OBSERVE, 1.0),
        (EvidenceMode.RISK_SIZING, ALIGNED, TimingFilterStatus.PASS, 1.0),
        (EvidenceMode.HARD_GATE, ALIGNED, TimingFilterStatus.PASS, 1.0),
        # Weak, missing, unavailable, or incomplete trend never blocks.
        (EvidenceMode.HARD_GATE, WEAK, TimingFilterStatus.OBSERVE, 1.0),
        (EvidenceMode.HARD_GATE, None, TimingFilterStatus.OBSERVE, 1.0),
        (EvidenceMode.HARD_GATE, {"available": False}, TimingFilterStatus.OBSERVE, 1.0),
        (EvidenceMode.HARD_GATE, {**ALIGNED, "complete": False}, TimingFilterStatus.OBSERVE, 1.0),
    ],
)
def test_mode_policy_matrix(mode, evidence, status, multiplier) -> None:
    result = MultiTimeframeTimingFilter(mode=mode).evaluate(evidence)

    assert result.status is status
    assert result.size_multiplier == multiplier
    assert result.filter_version == "multi_timeframe_timing_v1"


def test_multi_timeframe_plugin_emits_relative_change_for_timing_filter() -> None:
    from types import SimpleNamespace

    from nse_quant.research.evidence_plugins.mutli_timeframe import MultiTimeframeTrendPlugin

    candles = [SimpleNamespace(close=100.0), SimpleNamespace(close=101.0)]

    assert MultiTimeframeTrendPlugin._relative_change(candles) == pytest.approx(0.01)
