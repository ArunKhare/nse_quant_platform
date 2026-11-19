"""Pure reference-coverage planning, not Bronze/signature/native verification."""

import pytest

from nse_quant.data_platform.delegation_reference_coverage import plan_reference_coverage

A, B, C = "a" * 64, "b" * 64, "c" * 64


def test_every_signed_slot_has_exact_source():
    value = plan_reference_coverage((A, B, A), (B, A))
    assert value.exact_coverage
    assert value.binding_indices == (1, 0, 1)
    assert value.expected_slots == (A, B, A)


@pytest.mark.parametrize(
    "supplied,reason",
    [
        ((), "SIGNED_REFERENCE_SOURCE_MISSING"),
        ((A,), "SIGNED_REFERENCE_SOURCE_MISSING"),
        ((A, B, C), "UNSIGNED_EXTRA_REFERENCE_SOURCE"),
        ((A, A, B), "AMBIGUOUS_DUPLICATE_REFERENCE_SOURCE"),
    ],
    ids=["empty", "missing", "extra", "ambiguous"],
)
def test_no_missing_extra_or_first_source_wins(supplied, reason):
    value = plan_reference_coverage((A, B), supplied)
    assert not value.exact_coverage
    assert reason in value.reason_codes


def test_all_coverage_failures_retained():
    value = plan_reference_coverage((A, B), (A, A, C))
    assert len(value.reason_codes) == 3
    assert value.binding_indices[-1] == -1


@pytest.mark.parametrize(
    "expected,supplied",
    [
        ((), ()),
        ([A], (A,)),
        ((A,), [A]),
        ((A,) * 65, (A,)),
        ((A,), (A,) * 65),
        (("A" * 64,), (A,)),
        ((None,), (A,)),
        ((A,), (True,)),
    ],
    ids=[
        "empty-expected",
        "mutable-expected",
        "mutable-supplied",
        "expected-bound",
        "source-bound",
        "uppercase",
        "null",
        "bool",
    ],
)
def test_strict_immutable_bounded_keys(expected, supplied):
    with pytest.raises(ValueError):
        plan_reference_coverage(expected, supplied)


def test_maximum_slots_preserve_exact_duplicate_observations():
    value = plan_reference_coverage((A,) * 64, (A,))
    assert value.exact_coverage
    assert value.binding_indices == (0,) * 64


def test_ambiguous_slots_have_no_selected_source_index():
    value = plan_reference_coverage((A,), (A, A))
    assert value.binding_indices == (-1,)
    assert not value.exact_coverage
