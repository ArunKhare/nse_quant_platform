from __future__ import annotations

from nse_quant.research.paper_loop_vrp_readiness import (
    build_paper_loop_vrp_readiness_report,
    render_paper_loop_vrp_readiness_markdown,
)


def _payload() -> dict:
    return {
        "run_id": "paper-run-1",
        "captured_at": "2026-11-26T20:19:56Z",
        "paper_trading": True,
        "dry_run": True,
        "result": {
            "status": "vrp_gate_rejected",
            "rejection_reason": "variance_risk_premium_unavailable",
            "evidence": {
                "multi_timeframe_trend": {"available": True, "complete": True},
                "variance_risk_premium": {
                    "available": False,
                    "passed": False,
                    "gate_passed": False,
                    "estimator_gate_eligible": False,
                    "implied_volatility_gate_eligible": False,
                    "implied_volatility": 0.142431,
                    "implied_volatility_input": {
                        "source": "features.atm_iv",
                        "basis": "near_expiry_atm",
                        "constant_maturity_30d": False,
                        "as_of": "2026-11-26T15:31:00+05:30",
                    },
                    "expected_realized_volatility": None,
                    "expected_realized_volatility_input": {
                        "observations_available": 72,
                        "minimum_observations": 274,
                        "complete_sessions": 72,
                        "last_complete_session_age_days": 7,
                        "max_daily_close_age_days": 5,
                        "reason": "stale_or_missing_complete_intraday_sessions",
                        "calibration": {
                            "samples": 0,
                            "minimum_samples": 30,
                            "absolute_error_p90": None,
                        },
                        "trailing_close_to_close_fallback": {
                            "value": 0.1347,
                            "used_for_gate": False,
                        },
                    },
                    "variance_risk_premium": None,
                    "reasons": ["expected_realized_volatility_unavailable"],
                },
            },
        },
    }


def test_report_distinguishes_unavailable_vrp_from_negative_vrp() -> None:
    report = build_paper_loop_vrp_readiness_report(_payload())
    assert report["overall_status"] == "PAPER_LOOP_VRP_READINESS_BLOCKED"
    assert report["har_rv_readiness"]["status"] == "BLOCKED_HISTORY"
    assert report["har_rv_readiness"]["freshness_sufficient"] is False
    assert report["har_rv_readiness"]["calibration_sufficient"] is False
    assert report["iv30_source_readiness"]["status"] == "BLOCKED_NOT_30D_CONSTANT_MATURITY"
    assert report["vrp_gate_readiness"]["status"] == "BLOCKED_UNAVAILABLE"
    assert report["vrp_gate_readiness"]["variance_risk_premium"] is None
    assert report["india_vix_proxy_suitability"]["status"] == "NOT_EVALUATED_BY_PAPER_LOOP"
    assert report["authority"]["decision_eligibility_asserted"] is False


def test_report_handles_ready_inputs_but_still_requires_review() -> None:
    payload = _payload()
    vrp = payload["result"]["evidence"]["variance_risk_premium"]
    rv = vrp["expected_realized_volatility_input"]
    rv.update(
        observations_available=300,
        minimum_observations=274,
        last_complete_session_age_days=1,
        max_daily_close_age_days=5,
        reason=None,
        gate_eligible=True,
        calibration_gate_eligible=True,
        calibration={
            "samples": 35,
            "minimum_samples": 30,
            "absolute_error_p90": 0.02,
            "gate_margin_eligible": True,
        },
    )
    vrp.update(
        available=True,
        passed=True,
        gate_passed=True,
        estimator_gate_eligible=True,
        implied_volatility_gate_eligible=True,
        expected_realized_volatility=0.15,
        forecast_error_margin=0.02,
        implied_volatility_input={
            "source": "reviewed_internal_cm",
            "basis": "constant_maturity_30d",
            "constant_maturity_30d": True,
        },
        variance_risk_premium=0.001,
    )
    report = build_paper_loop_vrp_readiness_report(payload)
    assert report["overall_status"] == "PAPER_LOOP_VRP_INPUTS_READY_REVIEW_REQUIRED"
    assert report["har_rv_readiness"]["status"] == "READY"
    assert report["india_vix_proxy_suitability"]["status"] == "NOT_EVALUATED_BY_PAPER_LOOP"


def test_markdown_report_contains_authority_boundary() -> None:
    report = build_paper_loop_vrp_readiness_report(_payload())
    rendered = render_paper_loop_vrp_readiness_markdown(report)
    assert "An unavailable VRP is not a negative VRP" in rendered
    assert "India VIX proxy suitability" in rendered
