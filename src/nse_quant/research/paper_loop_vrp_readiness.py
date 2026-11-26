"""Read-only paper-loop and VRP evidence readiness reporting.

This report diagnoses supplied decision evidence. It never changes a gate,
infers India VIX proxy suitability, or grants decision/execution authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPORT_VERSION = "paper_loop_vrp_readiness_v1"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _stage(status: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **details}


def build_paper_loop_vrp_readiness_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic readiness diagnostics from one persisted loop result."""
    if not isinstance(payload, dict):
        raise ValueError("PAPER_LOOP_RESULT_OBJECT_REQUIRED")
    result = _mapping(payload.get("result")) or payload
    evidence = _mapping(result.get("evidence"))
    audit = _mapping(result.get("decision_audit"))
    if not evidence and audit:
        evidence = _mapping(audit.get("evidence"))
    vrp = _mapping(evidence.get("variance_risk_premium"))
    if not vrp:
        vrp = _mapping(audit.get("variance_risk_premium"))
    rv = _mapping(vrp.get("expected_realized_volatility_input"))
    calibration = _mapping(rv.get("calibration"))
    iv = _mapping(vrp.get("implied_volatility_input"))

    observations = rv.get("observations_available")
    minimum_observations = rv.get("minimum_observations")
    last_age = rv.get("last_complete_session_age_days")
    max_age = rv.get("max_daily_close_age_days")
    calibration_samples = calibration.get("samples", rv.get("calibration_samples"))
    calibration_minimum = calibration.get("minimum_samples", rv.get("calibration_minimum_samples", 30))
    forecast = _number(vrp.get("expected_realized_volatility"))
    calibration_margin = _number(vrp.get("forecast_error_margin"))
    rv_reason = rv.get("reason") or rv.get("forecast_reason")

    history_sufficient = (
        isinstance(observations, int)
        and isinstance(minimum_observations, int)
        and observations >= minimum_observations
    )
    freshness_sufficient = (
        isinstance(last_age, (int, float))
        and isinstance(max_age, (int, float))
        and last_age <= max_age
    )
    calibration_sufficient = (
        isinstance(calibration_samples, int)
        and isinstance(calibration_minimum, int)
        and calibration_samples >= calibration_minimum
        and calibration_margin is not None
        and calibration.get("gate_margin_eligible") is True
    )
    har_gate_eligible = rv.get("gate_eligible") is True
    if history_sufficient and freshness_sufficient and forecast is not None:
        har_status = "READY" if calibration_sufficient and har_gate_eligible else "BLOCKED_CALIBRATION"
    elif not history_sufficient:
        har_status = "BLOCKED_HISTORY"
    elif not freshness_sufficient:
        har_status = "BLOCKED_STALE_DATA"
    else:
        har_status = "BLOCKED_FORECAST"
    har = _stage(
        har_status,
        str(rv_reason or "HAR-RV forecast and calibration requirements evaluated from supplied evidence"),
        observations_available=observations,
        minimum_observations=minimum_observations,
        history_sufficient=history_sufficient,
        complete_sessions=rv.get("complete_sessions"),
        first_session_date=rv.get("first_session_date"),
        last_session_date=rv.get("last_session_date"),
        last_complete_session_age_days=last_age,
        max_daily_close_age_days=max_age,
        freshness_sufficient=freshness_sufficient,
        forecast_available=forecast is not None,
        forecast_volatility=forecast,
        calibration_samples=calibration_samples,
        calibration_minimum_samples=calibration_minimum,
        calibration_margin=calibration_margin,
        calibration_sufficient=calibration_sufficient,
        har_gate_eligible=har_gate_eligible,
        trailing_fallback=rv.get("trailing_close_to_close_fallback"),
        trailing_fallback_used_for_gate=False,
    )

    iv_source = iv.get("source")
    iv_basis = iv.get("basis")
    is_30d = iv.get("constant_maturity_30d") is True
    if is_30d:
        iv_status = "30D_CM_SOURCE_PRESENT_REVIEW_REQUIRED"
        iv_reason = "Input identifies a 30-day constant-maturity source; independent source and lineage validation remain required"
    elif iv_source is None:
        iv_status = "MISSING_IV_SOURCE_METADATA"
        iv_reason = "No implied-volatility source metadata was supplied"
    else:
        iv_status = "BLOCKED_NOT_30D_CONSTANT_MATURITY"
        iv_reason = "Paper-loop IV input is not identified as 30-day constant maturity"
    iv_readiness = _stage(
        iv_status,
        iv_reason,
        source=iv_source,
        basis=iv_basis,
        constant_maturity_30d=is_30d,
        implied_volatility=vrp.get("implied_volatility"),
        as_of=iv.get("as_of"),
    )

    vrp_available = vrp.get("available") is True
    vrp_passed = vrp.get("gate_passed") is True
    estimator_eligible = vrp.get("estimator_gate_eligible") is True
    iv_eligible = vrp.get("implied_volatility_gate_eligible") is True
    if vrp_passed:
        gate_status = "PASSED_FOR_THIS_PAPER_DECISION"
        gate_reason = "The supplied decision evidence records a passing VRP gate"
    elif not vrp_available:
        gate_status = "BLOCKED_UNAVAILABLE"
        gate_reason = "VRP is unavailable; this is not a measured negative VRP"
    elif not estimator_eligible:
        gate_status = "BLOCKED_ESTIMATOR_INELIGIBLE"
        gate_reason = "Realized-volatility estimator or calibration is not gate eligible"
    elif not iv_eligible:
        gate_status = "BLOCKED_IV_INPUT_INELIGIBLE"
        gate_reason = "Implied-volatility input is not gate eligible"
    else:
        gate_status = "REJECTED_BELOW_THRESHOLD"
        gate_reason = "VRP was available but did not clear the configured threshold"
    gate = _stage(
        gate_status,
        gate_reason,
        available=vrp_available,
        passed=vrp.get("passed") is True,
        gate_passed=vrp_passed,
        estimator_gate_eligible=estimator_eligible,
        implied_volatility_gate_eligible=iv_eligible,
        variance_risk_premium=vrp.get("variance_risk_premium"),
        minimum_vrp=vrp.get("minimum_vrp"),
        configured_minimum_vrp=vrp.get("configured_minimum_vrp"),
        forecast_error_margin=vrp.get("forecast_error_margin"),
        reasons=vrp.get("reasons") or result.get("rejection_reason"),
    )

    evidence_stages = {}
    for name, value in evidence.items():
        if name == "variance_risk_premium" or not isinstance(value, dict):
            continue
        evidence_stages[name] = {
            "available": value.get("available"),
            "complete": value.get("complete"),
            "status": value.get("status"),
            "mode": value.get("mode"),
            "reason": value.get("reason"),
            "missing": value.get("missing"),
            "reasons": value.get("reasons"),
        }

    proxy = _stage(
        "NOT_EVALUATED_BY_PAPER_LOOP",
        "Proxy suitability requires a separate synchronized India VIX versus internal_cm IV30 paired-source study, preregistered numerical policy, chronological holdout and human review",
        suitability_asserted=False,
        decision_eligibility_asserted=False,
        publication_asserted=False,
    )
    blockers = []
    if har_status != "READY":
        blockers.append("Restore complete, fresh HAR-RV history and eligible walk-forward calibration")
    if not is_30d:
        blockers.append("Provide a separately validated 30-day constant-maturity IV input; near-expiry ATM IV is not a substitute")
    if not vrp_passed:
        blockers.append("Keep new entries blocked until the unchanged VRP gate has eligible inputs and passes")
    blockers.append("Run the independent India VIX/internal_cm proxy study; paper-loop results do not establish proxy suitability")

    report = {
        "report_version": REPORT_VERSION,
        "run_id": payload.get("run_id"),
        "captured_at": payload.get("captured_at"),
        "decision_status": result.get("status"),
        "rejection_reason": result.get("rejection_reason"),
        "paper_trading": payload.get("paper_trading", audit.get("paper_trading")),
        "dry_run": payload.get("dry_run", audit.get("dry_run")),
        "har_rv_readiness": har,
        "iv30_source_readiness": iv_readiness,
        "vrp_gate_readiness": gate,
        "other_evidence_stages": evidence_stages,
        "india_vix_proxy_suitability": proxy,
        "overall_status": (
            "PAPER_LOOP_VRP_INPUTS_READY_REVIEW_REQUIRED"
            if har_status == "READY" and is_30d and vrp_passed
            else "PAPER_LOOP_VRP_READINESS_BLOCKED"
        ),
        "blockers_and_next_actions": blockers,
        "authority": {
            "decision_eligibility_asserted": False,
            "publication_asserted": False,
            "trading_authority_asserted": False,
            "report_is_observational": True,
        },
    }
    return report


def render_paper_loop_vrp_readiness_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable report from its structured representation."""
    har = _mapping(report.get("har_rv_readiness"))
    iv = _mapping(report.get("iv30_source_readiness"))
    vrp = _mapping(report.get("vrp_gate_readiness"))
    proxy = _mapping(report.get("india_vix_proxy_suitability"))
    lines = [
        "# Paper Loop + VRP Readiness Report",
        "",
        f"- Run ID: {report.get('run_id') or 'not supplied'}",
        f"- Captured at: {report.get('captured_at') or 'not supplied'}",
        f"- Decision status: {report.get('decision_status') or 'not supplied'}",
        f"- Overall: **{report.get('overall_status')}**",
        "",
        "## 1. HAR-RV readiness",
        f"- Status: **{har.get('status')}**",
        f"- Complete observations: {har.get('observations_available')} / {har.get('minimum_observations')}",
        f"- Last complete session age: {har.get('last_complete_session_age_days')} days (maximum {har.get('max_daily_close_age_days')})",
        f"- Forecast available: {har.get('forecast_available')}",
        f"- Calibration samples: {har.get('calibration_samples')} / {har.get('calibration_minimum_samples')}",
        f"- Calibration margin: {har.get('calibration_margin')}",
        f"- Reason: {har.get('reason')}",
        "",
        "## 2. Implied-volatility source readiness",
        f"- Status: **{iv.get('status')}**",
        f"- Source / basis: {iv.get('source')} / {iv.get('basis')}",
        f"- 30-day constant maturity: {iv.get('constant_maturity_30d')}",
        f"- Reason: {iv.get('reason')}",
        "",
        "## 3. VRP gate",
        f"- Status: **{vrp.get('status')}**",
        f"- Available / passed: {vrp.get('available')} / {vrp.get('gate_passed')}",
        f"- VRP: {vrp.get('variance_risk_premium')}",
        f"- Reason: {vrp.get('reason')}",
        "",
        "## 4. India VIX proxy suitability",
        f"- Status: **{proxy.get('status')}**",
        f"- {proxy.get('reason')}",
        "",
        "## 5. Blockers and next actions",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(report.get("blockers_and_next_actions", []), 1))
    lines.extend(
        [
            "",
            "## Authority boundary",
            "This report is observational. It does not establish proxy suitability, decision eligibility, publication authority or trading authority. An unavailable VRP is not a negative VRP.",
            "",
        ]
    )
    return "\n".join(lines)


def load_paper_loop_payload(path: str | Path) -> dict[str, Any]:
    """Load the exact JSON artifact emitted by the paper-loop runner."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PAPER_LOOP_RESULT_OBJECT_REQUIRED")
    return value
