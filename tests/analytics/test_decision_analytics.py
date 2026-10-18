from datetime import UTC, datetime
from uuid import uuid4

from nse_quant.analytics.decision_analytics import (
    DecisionAnalyticsRepository,
)


def test_feature_gate_summary_counts_pass_and_rejection(
    test_store,
) -> None:
    repository = DecisionAnalyticsRepository(test_store)
    ts = datetime.now(UTC)

    for passed in [True, False, False]:
        test_store.write_feature_gate_result(
            gate_result_id=uuid4().hex,
            ts=ts,
            run_id="analytics-run",
            symbol="NIFTY",
            passed=passed,
            reasons=["test_rejection"] if not passed else [],
            checks={"feature_snapshot_available": passed},
        )

    summary = repository.feature_gate_summary(run_id="analytics-run")

    assert len(summary) == 2
    assert set(summary["passed"]) == {True, False}
    assert summary["cycles"].sum() == 3


def test_rejection_reasons_groups_by_reason(test_store) -> None:
    repository = DecisionAnalyticsRepository(test_store)
    ts = datetime.now(UTC)

    for reason in ["realized_vol_out_of_range", "realized_vol_out_of_range"]:
        test_store.write_feature_gate_result(
            gate_result_id=uuid4().hex,
            ts=ts,
            run_id="analytics-run",
            symbol="NIFTY",
            passed=False,
            reasons=[reason],
            checks={"realized_vol_in_range": False},
        )

    reasons = repository.rejection_reasons(run_id="analytics-run")

    assert len(reasons) == 1
    assert reasons.iloc[0]["reason"] == "realized_vol_out_of_range"
    assert reasons.iloc[0]["occurrences"] == 2