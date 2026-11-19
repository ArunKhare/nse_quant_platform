"""Tests for the native iron-condor operational acceptance harness."""

from __future__ import annotations

import pytest

from nse_quant.data_platform.native_iron_condor_decision_run_orchestrator import (
    NativeDecisionRunRequest,
)
from nse_quant.data_platform.native_iron_condor_operational_acceptance import (
    run_native_iron_condor_operational_acceptance,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _plan() -> dict[str, object]:
    return {
        "version": "native-iron-condor-operational-acceptance@1",
        "trading_days": [
            {"trading_date": "2026-11-16"},
            {"trading_date": "2026-11-17"},
        ],
    }


def _requests() -> list[NativeDecisionRunRequest]:
    return [
        NativeDecisionRunRequest(
            run_id=f"acceptance-run-{index}",
            actor_id="researcher",
            code_revision="a" * 40,
            strategy_bundle=None,
            portfolio_risk_bundle=None,
        )
        for index in range(2)
    ]


def _coverage_reports() -> list[dict[str, object]]:
    return [{}, {}]


def _boundaries() -> list[dict[str, object]]:
    return [{"run_id": f"acceptance-run-{index}"} for index in range(2)]


def test_plan_length_mismatch_rejected() -> None:
    with pytest.raises(Rejected, match="ACCEPTANCE_PLAN_LENGTH_MISMATCH"):
        run_native_iron_condor_operational_acceptance(
            None,
            None,
            None,
            plan=_plan(),
            requests=_requests()[:1],
            coverage_reports=_coverage_reports(),
            authoritative_boundaries=_boundaries(),
        )


def test_invalid_plan_rejected() -> None:
    plan = _plan()
    plan["version"] = "wrong"
    with pytest.raises(Rejected, match="ACCEPTANCE_PLAN_VERSION_MISMATCH"):
        run_native_iron_condor_operational_acceptance(
            None,
            None,
            None,
            plan=plan,
            requests=_requests(),
            coverage_reports=_coverage_reports(),
            authoritative_boundaries=_boundaries(),
        )
