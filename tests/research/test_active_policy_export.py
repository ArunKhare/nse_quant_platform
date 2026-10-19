from datetime import UTC, datetime
from pathlib import Path

from scripts.export_active_policy import build_active_policy


def test_missing_policy_is_not_actionable() -> None:
    result = build_active_policy(
        symbol="NIFTY",
        policy=None,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is False
    assert result["selection_status"] == "UNAVAILABLE"
    assert result["reason"] == "no_policy_available"


def test_ready_current_policy_is_actionable() -> None:
    policy = {
        "policy_id": "NIFTY:2026-07-22:2026-09-22",
        "allowed_regimes": {"RANGE|HIGH"},
        "selection_status": "READY",
        "test_end": datetime(2026, 12, 31).date(),
        "risk_limits": {
            "RANGE|HIGH": {
                "allowed": True,
                "max_lots_per_order": 1,
            }
        },
    }

    result = build_active_policy(
        symbol="NIFTY",
        policy=policy,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is True
    assert result["reason"] == "active"
    assert result["allowed_regimes"] == ["RANGE|HIGH"]


def test_expired_ready_policy_is_not_actionable() -> None:
    policy = {
        "policy_id": "NIFTY:2026-01-01:2026-03-01",
        "allowed_regimes": {"RANGE|HIGH"},
        "selection_status": "READY",
        "test_end": datetime(2026, 3, 1).date(),
        "risk_limits": {},
    }

    result = build_active_policy(
        symbol="NIFTY",
        policy=policy,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is False
    assert result["reason"] == "policy_expired"