"""Multi-complete-trading-day reliability evidence; research evaluator only,
no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TradingDayRecord:
    trading_day: date
    cycles_run: int
    cycles_passed: int
    evidence_complete: bool
    kill_switch_triggered: bool
    errors: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "trading_day": self.trading_day.isoformat(),
            "cycles_run": self.cycles_run,
            "cycles_passed": self.cycles_passed,
            "evidence_complete": self.evidence_complete,
            "kill_switch_triggered": self.kill_switch_triggered,
            "errors": self.errors,
            "decision_eligibility_asserted": False,
        }


@dataclass(frozen=True)
class ReliabilitySettings:
    min_days: int = 3
    min_cycles_per_day: int = 1
    max_errors_per_day: int = 0
    require_evidence_complete: bool = True
    allow_kill_switch: bool = False


def evaluate_reliability(
    *,
    records: list[TradingDayRecord],
    settings: ReliabilitySettings | None = None,
) -> dict[str, Any]:
    settings = settings or ReliabilitySettings()
    total_days = len(records)
    if total_days < settings.min_days:
        return {
            "status": "INSUFFICIENT_DAYS",
            "reason": "insufficient_trading_days",
            "total_days": total_days,
            "required_days": settings.min_days,
            "decision_eligibility_asserted": False,
        }

    failures: list[str] = []
    total_cycles = 0
    total_passed = 0
    total_errors = 0
    days_with_kill_switch = 0
    days_incomplete_evidence = 0

    for record in records:
        total_cycles += record.cycles_run
        total_passed += record.cycles_passed
        total_errors += record.errors
        if record.kill_switch_triggered:
            days_with_kill_switch += 1
        if not record.evidence_complete:
            days_incomplete_evidence += 1
        if record.cycles_run < settings.min_cycles_per_day:
            failures.append(f"{record.trading_day.isoformat()}:insufficient_cycles")
        if record.cycles_passed < record.cycles_run:
            failures.append(f"{record.trading_day.isoformat()}:cycles_not_all_passed")
        if record.errors > settings.max_errors_per_day:
            failures.append(f"{record.trading_day.isoformat()}:errors_exceeded")
        if settings.require_evidence_complete and not record.evidence_complete:
            failures.append(f"{record.trading_day.isoformat()}:evidence_incomplete")
        if not settings.allow_kill_switch and record.kill_switch_triggered:
            failures.append(f"{record.trading_day.isoformat()}:kill_switch_triggered")

    pass_rate = total_passed / total_cycles if total_cycles else 0.0
    status = "RELIABILITY_EVIDENCE_COMPLETE" if not failures else "RELIABILITY_GAPS_FOUND"

    return {
        "status": status,
        "total_days": total_days,
        "total_cycles": total_cycles,
        "total_passed_cycles": total_passed,
        "total_errors": total_errors,
        "days_with_kill_switch": days_with_kill_switch,
        "days_incomplete_evidence": days_incomplete_evidence,
        "pass_rate": pass_rate,
        "failures": failures,
        "settings": {
            "min_days": settings.min_days,
            "min_cycles_per_day": settings.min_cycles_per_day,
            "max_errors_per_day": settings.max_errors_per_day,
            "require_evidence_complete": settings.require_evidence_complete,
            "allow_kill_switch": settings.allow_kill_switch,
        },
        "decision_eligibility_asserted": False,
    }


def summarize_reliability(records: list[TradingDayRecord]) -> dict[str, Any]:
    total_days = len(records)
    total_cycles = sum(r.cycles_run for r in records)
    total_passed = sum(r.cycles_passed for r in records)
    total_errors = sum(r.errors for r in records)
    return {
        "total_days": total_days,
        "total_cycles": total_cycles,
        "total_passed_cycles": total_passed,
        "total_errors": total_errors,
        "pass_rate": total_passed / total_cycles if total_cycles else 0.0,
        "decision_eligibility_asserted": False,
    }
