from datetime import UTC, datetime

from scripts.export_active_policy import build_active_policy

REGIME = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"


def test_missing_policy_is_not_actionable() -> None:
    result = build_active_policy(
        symbol="NIFTY",
        policy=None,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is False
    assert result["selection_status"] == "UNAVAILABLE"
    assert result["reason"] == "no_policy_available"
    assert result["regime_vocabulary"] is None


def test_ready_current_policy_is_actionable() -> None:
    policy = {
        "policy_id": "NIFTY:2026-07-22:2026-09-22",
        "allowed_regimes": {REGIME},
        "selection_status": "READY",
        "regime_vocabulary": "canonical_v1",
        "test_end": datetime(2026, 12, 31).date(),
        "risk_limits": {
            REGIME: {
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
    assert result["allowed_regimes"] == [REGIME]


def test_expired_ready_policy_is_not_actionable() -> None:
    policy = {
        "policy_id": "NIFTY:2026-01-01:2026-03-01",
        "allowed_regimes": {REGIME},
        "selection_status": "READY",
        "regime_vocabulary": "canonical_v1",
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
def test_legacy_or_unversioned_policy_is_not_actionable() -> None:
    policy = {
        "policy_id": "NIFTY:legacy",
        "allowed_regimes": {REGIME},
        "selection_status": "READY",
        "regime_vocabulary": "legacy_daily_v0",
        "test_end": datetime(2026, 12, 31).date(),
        "risk_limits": {REGIME: {"allowed": True}},
    }

    result = build_active_policy(
        symbol="NIFTY",
        policy=policy,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is False
    assert result["selection_status"] == "INVALID_POLICY"
    assert result["reason"] == "canonical_policy_validation_failed"
    assert result["regime_vocabulary"] == "legacy_daily_v0"


def test_noncanonical_risk_limit_key_is_not_exported() -> None:
    policy = {
        "policy_id": "NIFTY:malformed",
        "allowed_regimes": {REGIME},
        "selection_status": "READY",
        "regime_vocabulary": "canonical_v1",
        "test_end": datetime(2026, 12, 31).date(),
        "risk_limits": {"BULL|NORMAL": {"allowed": True}},
    }

    result = build_active_policy(
        symbol="NIFTY",
        policy=policy,
        as_of=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert result["actionable"] is False
    assert result["allowed_regimes"] == []
    assert result["risk_limits"] == {}
    assert result["regime_registry_version"]
