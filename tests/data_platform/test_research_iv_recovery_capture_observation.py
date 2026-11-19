"""Pure byte-comparison tests. No canonical/native/audit truth inferred from these bytes."""

import hashlib
from dataclasses import asdict
from typing import Any

import pytest

from nse_quant.data_platform import research_iv_recovery_capture_observation as observation


@pytest.mark.parametrize(
    "first,second,expected",
    [
        (b"recorded", b"recorded", (True, True, True)),
        (b"changed", b"recorded", (False, True, False)),
        (b"recorded", b"changed", (True, False, False)),
        (b"changed", b"changed", (False, False, True)),
        (b"changed", b"different", (False, False, False)),
    ],
    ids=["match", "bad-good", "good-bad", "stable-different", "both-different"],
)
def test_exact_comparison_keeps_both_orderings(first, second, expected):
    value = observation.compare_recovery_capture_plans(b"recorded", first, second)
    assert (
        value.first_matches_recorded_plan,
        value.second_matches_recorded_plan,
        value.native_plans_match,
    ) == expected
    assert value.all_plan_bytes_match == all(expected)
    assert len(value.reason_codes) == sum(not flag for flag in expected)
    assert value.first_plan_sha256 == hashlib.sha256(first).hexdigest()
    assert value.second_plan_sha256 == hashlib.sha256(second).hexdigest()
    assert value == observation.compare_recovery_capture_plans(b"recorded", first, second)


@pytest.mark.parametrize("position", range(3), ids=["recorded", "first", "second"])
@pytest.mark.parametrize(
    "bad", [b"", bytearray(b"x"), "x", None], ids=["empty", "mutable", "text", "none"]
)
def test_bad_input_never_accepts_prefix(position, bad):
    inputs: list[Any] = [b"valid", b"valid", b"valid"]
    inputs[position] = bad
    with pytest.raises(ValueError, match="BOUNDED_PLAN_BYTES_REQUIRED"):
        observation.compare_recovery_capture_plans(*inputs)


def test_byte_bound_inclusive_and_oversize_rejected(monkeypatch):
    monkeypatch.setattr(observation, "MAX_PLAN_BYTES", 4)
    value = observation.compare_recovery_capture_plans(b"abcd", b"abcd", b"abcd")
    assert value.all_plan_bytes_match
    with pytest.raises(ValueError, match="BOUNDED_PLAN_BYTES_REQUIRED"):
        observation.compare_recovery_capture_plans(b"abcde", b"abcd", b"abcd")


def test_equal_scalar_or_digest_field_is_not_complete_plan_equality():
    first = b'{"evidence_fingerprint":"same","entries":[1]}'
    second = b'{"evidence_fingerprint":"same","entries":[2]}'
    value = observation.compare_recovery_capture_plans(first, first, second)
    assert not value.all_plan_bytes_match
    assert not value.second_matches_recorded_plan
    assert value.first_matches_recorded_plan


def test_whitespace_and_order_are_not_normalized():
    value = observation.compare_recovery_capture_plans(b'{"a":1}', b'{"a": 1}', b'{"a":1}')
    assert not value.all_plan_bytes_match
    assert value.second_matches_recorded_plan


def test_comparison_contains_only_hashes_flags_codes_and_version():
    value = observation.compare_recovery_capture_plans(b"private", b"private", b"private")
    assert "private" not in str(asdict(value))
    assert len(value.evidence_fingerprint) == 64


def test_service_defaults_and_signature_do_not_escalate_evidence():
    import inspect
    from dataclasses import fields

    from nse_quant.data_platform import research_iv_recovery_capture_revalidation as service

    signature = inspect.signature(service.revalidate_research_iv_recovery_capture)
    assert set(signature.parameters) == {
        "staging",
        "capture",
        "capture_build_id_pin",
        "expected_capture_fingerprint",
        "artifact_root",
    }
    value = service.ResearchIvCurrentRecoveryCapture(
        service.VERSION,
        "a" * 64,
        "b" * 64,
        "review_required",
        ("SYNTHETIC",),
    )
    for field in fields(value):
        if field.name.endswith(
            (
                "_checked",
                "_verified",
                "_authorized",
                "_asserted",
                "_determined",
                "_reproduced",
                "_observed",
            )
        ):
            assert getattr(value, field.name) is False
    assert value.evidence_fingerprint is None and value.plan_evidence_fingerprint is None
