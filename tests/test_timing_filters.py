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
