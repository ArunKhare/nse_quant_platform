"""Pure sequence/pin constraints, not signed/native policy verification."""

from dataclasses import replace
from typing import cast

import pytest

from nse_quant.data_platform.policy_window import (
    PolicyPosition,
    PolicyWindowEntry,
    check_policy_window,
)


def entry(seq, digest=None, denied=(), policy_id="TEST"):
    return PolicyWindowEntry(policy_id, PolicyPosition(seq, digest or f"{seq:064x}"), denied)


def check(entries, **changes):
    arguments = dict(anchor=entries[0].position, tip=entries[-1].position)
    arguments.update(changes)
    return check_policy_window(tuple(entries), **arguments)


def test_contiguous_window_does_not_prove_latest_or_authority():
    value = check([entry(10), entry(11), entry(12)])
    assert value.window_constraints_satisfied
    assert not value.policy_currentness_verified
    assert not value.policy_authority_authenticated
    assert not value.authorized_key_reactivation_asserted
    assert not value.decision_eligibility_asserted


def test_exact_consecutive_retry_preserved():
    value = check([entry(1), entry(1), entry(2)])
    assert value.window_constraints_satisfied
    assert value.observed_sequences == (1, 1, 2)
    assert value.exact_retry_count == 1


def test_same_sequence_fork_is_not_retry():
    value = check([entry(1), entry(1, "f" * 64)])
    assert "POLICY_WINDOW_SAME_SEQUENCE_FORK" in value.reason_codes
    assert not value.window_constraints_satisfied


def test_observed_rollback_cannot_hide_behind_return_to_tip():
    value = check([entry(1), entry(2), entry(1), entry(2)])
    assert "POLICY_WINDOW_OBSERVED_ROLLBACK" in value.reason_codes


def test_gap_not_filled_by_numeric_tip():
    value = check([entry(1), entry(3)])
    assert "POLICY_WINDOW_SEQUENCE_GAP" in value.reason_codes


def test_denial_removal_requires_different_contract():
    value = check([entry(1, denied=("a" * 64,)), entry(2)])
    assert "POLICY_WINDOW_DENIAL_REMOVAL_REQUIRES_NEW_CONTRACT" in value.reason_codes


def test_denials_may_accumulate():
    value = check([entry(1), entry(2, denied=("a" * 64,)), entry(3, denied=("a" * 64, "b" * 64))])
    assert value.window_constraints_satisfied


def test_series_never_selected_by_highest_sequence():
    value = check([entry(1), entry(2, policy_id="OTHER")])
    assert "POLICY_WINDOW_SERIES_MISMATCH" in value.reason_codes


@pytest.mark.parametrize("endpoint", ["anchor", "tip"])
def test_exact_endpoint_pins(endpoint):
    entries = [entry(1), entry(2)]
    original = entries[0].position if endpoint == "anchor" else entries[-1].position
    value = check(entries, **{endpoint: replace(original, policy_sha256="e" * 64)})
    assert not value.window_constraints_satisfied


@pytest.mark.parametrize("sequence", [True, 0, -1, 2147483648])
def test_sequence_bounds(sequence):
    with pytest.raises(ValueError):
        PolicyPosition(sequence, "a" * 64)


@pytest.mark.parametrize("digest", ["A" * 64, "x", None])
def test_exact_pin(digest):
    with pytest.raises(ValueError):
        PolicyPosition(1, digest)


def test_window_capacity_and_immutability():
    with pytest.raises(ValueError):
        check_policy_window(
            cast(tuple[PolicyWindowEntry, ...], []),
            anchor=entry(1).position,
            tip=entry(1).position,
        )
    for values in ((), tuple(entry(i + 1) for i in range(65))):
        with pytest.raises(ValueError):
            check_policy_window(values, anchor=entry(1).position, tip=entry(1).position)


def test_denied_key_bounds_and_duplicates():
    for keys in (("a" * 64, "a" * 64), ("bad",), tuple(f"{i:064x}" for i in range(129))):
        with pytest.raises(ValueError):
            entry(1, denied=keys)


def test_endpoint_order():
    with pytest.raises(ValueError, match="ORDER_INVALID"):
        check_policy_window((entry(2),), anchor=entry(2).position, tip=entry(1).position)


def test_same_pin_cannot_represent_different_denials():
    value = check([entry(1), entry(1, denied=("a" * 64,))])
    assert "POLICY_WINDOW_SAME_PIN_PROJECTION_MISMATCH" in value.reason_codes
