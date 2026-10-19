from scripts.regime_coverage_report import coverage_tier


def test_coverage_tiers() -> None:
    assert coverage_tier(0) == "INSUFFICIENT"
    assert coverage_tier(9) == "INSUFFICIENT"
    assert coverage_tier(10) == "INITIAL_EVIDENCE"
    assert coverage_tier(29) == "INITIAL_EVIDENCE"
    assert coverage_tier(30) == "USABLE"
    assert coverage_tier(99) == "USABLE"
    assert coverage_tier(100) == "STRONG"
    assert coverage_tier(299) == "STRONG"
    assert coverage_tier(300) == "ROBUST"