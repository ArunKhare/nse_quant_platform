"""Tests for refusal-to-lifecycle-recovery integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_lifecycle_recovery_integration import (
    integrate_refusal_into_lifecycle_recovery,
)


def _valid_refusal_admission_result():
    return dict(
        integrated=True,
        reason="REFUSAL_INTEGRATED_INTO_ADMISSION",
        eligible=True,
    )


def _valid_original_obligations():
    return dict(
        obligation_1="failed",
        obligation_2="incomplete",
        obligation_3="unlinked",
        obligation_4="orphan",
    )


def _valid_recovery_outcomes():
    return dict(
        obligation_1="review_required",
        obligation_2="review_required",
        obligation_3="review_required",
        obligation_4="review_required",
    )


def test_valid_refusal_admission_result_integrated():
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=_valid_refusal_admission_result(),
        original_obligations=_valid_original_obligations(),
        recovery_outcomes=_valid_recovery_outcomes(),
    )
    assert result["integrated"] is True
    assert result["reason"] == "REFUSAL_INTEGRATED_INTO_LIFECYCLE_RECOVERY"
    assert result["reconciled"] is True


def test_non_dict_refusal_admission_result_refused():
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result="not_a_dict",
        original_obligations=_valid_original_obligations(),
        recovery_outcomes=_valid_recovery_outcomes(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_ADMISSION_RESULT_OBJECT_REQUIRED"
    assert result["reconciled"] is False


def test_refusal_not_integrated_rejected():
    candidate = _valid_refusal_admission_result()
    candidate["integrated"] = False
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=candidate,
        original_obligations=_valid_original_obligations(),
        recovery_outcomes=_valid_recovery_outcomes(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_ADMISSION"
    assert result["reconciled"] is False


def test_missing_integrated_flag_defaults_to_false():
    candidate = _valid_refusal_admission_result()
    del candidate["integrated"]
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=candidate,
        original_obligations=_valid_original_obligations(),
        recovery_outcomes=_valid_recovery_outcomes(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_ADMISSION"
    assert result["reconciled"] is False


def test_non_dict_original_obligations_refused():
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=_valid_refusal_admission_result(),
        original_obligations="not_a_dict",
        recovery_outcomes=_valid_recovery_outcomes(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "ORIGINAL_OBLIGATIONS_DICT_REQUIRED"
    assert result["reconciled"] is False


def test_non_dict_recovery_outcomes_refused():
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=_valid_refusal_admission_result(),
        original_obligations=_valid_original_obligations(),
        recovery_outcomes="not_a_dict",
    )
    assert result["integrated"] is False
    assert result["reason"] == "RECOVERY_OUTCOMES_DICT_REQUIRED"
    assert result["reconciled"] is False


def test_original_obligation_healed_rejected():
    candidate = _valid_recovery_outcomes()
    candidate["obligation_1"] = "resolved"
    result = integrate_refusal_into_lifecycle_recovery(
        refusal_admission_result=_valid_refusal_admission_result(),
        original_obligations=_valid_original_obligations(),
        recovery_outcomes=candidate,
    )
    assert result["integrated"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_NOT_RECONCILED"
    assert result["reconciled"] is False
