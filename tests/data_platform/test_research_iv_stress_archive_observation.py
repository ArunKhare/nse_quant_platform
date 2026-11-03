"""Pure exact-byte comparison and API/denial tests; no native dependency substitutes."""

import hashlib
import inspect
from dataclasses import fields
from typing import Any

import pytest

from nse_quant.data_platform import research_iv_stress_archive_observation as observation
from nse_quant.data_platform import research_iv_stress_archive_revalidation as service


@pytest.mark.parametrize(
    "first,second,flags",
    [
        (b"original", b"original", (True, True, True)),
        (b"bad", b"original", (False, True, False)),
        (b"original", b"bad", (True, False, False)),
        (b"bad", b"bad", (False, False, True)),
        (b"bad", b"other", (False, False, False)),
    ],
    ids=["match", "bad-good", "good-bad", "stable-different", "both-different"],
)
def test_full_bytes_both_orderings_and_hashes(first, second, flags):
    value = observation.compare_iv_stress_archive_observations(b"original", first, second)
    assert (
        value.first_matches_recording,
        value.second_matches_recording,
        value.current_observations_match,
    ) == flags
    assert value.all_observations_match == all(flags)
    assert len(value.reason_codes) == sum(not flag for flag in flags)
    assert value.recorded_sha256 == hashlib.sha256(b"original").hexdigest()
    assert value.first_sha256 == hashlib.sha256(first).hexdigest()
    assert value.second_sha256 == hashlib.sha256(second).hexdigest()
    assert value == observation.compare_iv_stress_archive_observations(b"original", first, second)


@pytest.mark.parametrize("position", range(3), ids=["recording", "first", "second"])
@pytest.mark.parametrize(
    "bad", [b"", bytearray(b"x"), "x", None], ids=["empty", "mutable", "text", "none"]
)
def test_bad_payloads_never_accept_prefix(position, bad):
    args: list[Any] = [b"valid", b"valid", b"valid"]
    args[position] = bad
    with pytest.raises(ValueError, match="BOUNDED_IMMUTABLE"):
        observation.compare_iv_stress_archive_observations(*args)


def test_inclusive_byte_bound_and_overflow_rejection(monkeypatch):
    monkeypatch.setattr(observation, "MAX_OBSERVATION_BYTES", 4)
    result = observation.compare_iv_stress_archive_observations(b"abcd", b"abcd", b"abcd")
    assert result.all_observations_match
    with pytest.raises(ValueError, match="BOUNDED_IMMUTABLE"):
        observation.compare_iv_stress_archive_observations(b"abcde", b"abcd", b"abcd")


def test_matching_study_scalar_is_not_complete_native_equality():
    original = b'{"study":{"price":1},"before":{"source":1}}'
    changed = b'{"study":{"price":1},"before":{"source":2}}'
    result = observation.compare_iv_stress_archive_observations(original, original, changed)
    assert result.first_matches_recording and not result.second_matches_recording
    assert not result.all_observations_match


def test_no_normalizing_whitespace_or_later_good_selection():
    result = observation.compare_iv_stress_archive_observations(
        b'{"iv":1}',
        b'{"iv": 1}',
        b'{"iv":1}',
    )
    assert not result.all_observations_match and not result.current_observations_match
    assert result.second_matches_recording


def test_new_service_signature_and_defaults_deny_admission():
    signature = inspect.signature(service.revalidate_research_iv_spot_stress_archive)
    assert set(signature.parameters) == {
        "bronze",
        "frame_silver",
        "reference_silver",
        "assessments",
        "source_gold",
        "archive",
        "stress_archive",
        "stress_record_id_pin",
        "expected_recording_fingerprint",
    }
    value = service.ResearchIvCurrentStressArchive(
        service.VERSION,
        "a" * 64,
        "b" * 64,
        "review_required",
        ("SYNTHETIC",),
    )
    for field in fields(value):
        if field.name.endswith(
            (
                "_verified",
                "_checked",
                "_rechecked",
                "_reproduced",
                "_observed",
                "_asserted",
                "_modelled",
                "_authoritative",
            )
        ):
            assert getattr(value, field.name) is False
    assert value.study is None and value.native_stress_fingerprint is None
    assert value.evidence_fingerprint is None
    assert value.canonical_contract_id is None
    assert value.event_ts is None and value.published_at is None
