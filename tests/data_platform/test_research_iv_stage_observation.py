"""Pure comparison fixtures; not simulated successful native/stage computations."""

import hashlib
from dataclasses import fields
from itertools import product
from typing import cast

import pytest

from nse_quant.data_platform import research_iv_stage_observation as observation


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def compare(items, **changes):
    arguments = dict(
        recorded_before_sha256=digest(b"native-A"),
        recorded_after_sha256=digest(b"native-A"),
        expected_bundle_id=digest(b"artifact-A"),
    )
    arguments.update(changes)
    return observation.compare_iv_stage_observations(*items, **arguments)


CASES = list(product((False, True), repeat=4))


@pytest.mark.parametrize("changed", CASES, ids=[f"case-{index:02d}" for index in range(16)])
def test_all_digest_and_byte_negative_orderings(changed):
    raw = [b"native-A", b"native-A", b"artifact-A", b"artifact-A"]
    for index, change in enumerate(changed):
        if change:
            raw[index] += b"-changed"
    value = compare(raw)
    assert value.first_matches_recorded_digest is (not changed[0])
    assert value.second_matches_recorded_digest is (not changed[1])
    assert value.first_artifact_matches_pin is (not changed[2])
    assert value.second_artifact_matches_pin is (not changed[3])
    assert value.native_observations_match is (raw[0] == raw[1])
    assert value.artifact_observations_match is (raw[2] == raw[3])
    assert value.all_observations_match is (not any(changed))
    assert value == compare(raw)


@pytest.mark.parametrize("position", range(4), ids=["native1", "native2", "artifact1", "artifact2"])
@pytest.mark.parametrize(
    "bad", [b"", bytearray(b"x"), "x", None], ids=["empty", "mutable", "text", "none"]
)
def test_exact_immutable_bytes_for_every_role(position, bad):
    items = [b"native-A", b"native-A", b"artifact-A", b"artifact-A"]
    items[position] = cast(bytes, bad)
    with pytest.raises(ValueError, match="BOUNDED_IMMUTABLE"):
        compare(items)


@pytest.mark.parametrize(
    "field",
    [
        "recorded_before_sha256",
        "recorded_after_sha256",
        "expected_bundle_id",
    ],
    ids=["before", "after", "bundle"],
)
def test_exact_pins_in_every_role(field):
    with pytest.raises(ValueError):
        compare([b"native-A", b"native-A", b"artifact-A", b"artifact-A"], **{field: "BAD"})


def test_different_original_digests_cannot_be_promoted():
    with pytest.raises(ValueError):
        compare(
            [b"native-A", b"native-A", b"artifact-A", b"artifact-A"],
            recorded_after_sha256=digest(b"different"),
        )


def test_native_and_artifact_limits_checked_independently(monkeypatch):
    monkeypatch.setattr(observation, "MAX_NATIVE_BYTES", 3)
    monkeypatch.setattr(observation, "MAX_ARTIFACT_BYTES", 2)
    arguments = dict(
        recorded_before_sha256=digest(b"aaa"),
        recorded_after_sha256=digest(b"aaa"),
        expected_bundle_id=digest(b"bb"),
    )
    good = [b"aaa", b"aaa", b"bb", b"bb"]
    assert observation.compare_iv_stage_observations(*good, **arguments).all_observations_match
    for index in range(4):
        bad = good[:]
        bad[index] += b"x"
        with pytest.raises(ValueError):
            observation.compare_iv_stage_observations(*bad, **arguments)


def test_later_good_is_never_selected_over_earlier_negative():
    value = compare([b"native-bad", b"native-A", b"artifact-A", b"artifact-A"])
    assert not value.first_matches_recorded_digest and value.second_matches_recorded_digest
    assert not value.all_observations_match
    assert "CURRENT_IV_STAGE_NATIVE_OBSERVATIONS_DIFFER" in value.reason_codes


def test_matching_current_pair_does_not_match_original_recording():
    value = compare([b"new-runtime", b"new-runtime", b"artifact-A", b"artifact-A"])
    assert value.native_observations_match
    assert not value.first_matches_recorded_digest and not value.second_matches_recorded_digest
    assert not value.all_observations_match


def test_no_numeric_metadata_or_whitespace_normalization():
    original = b'{"iv":0.2,"runtime":"A"}'
    for changed in (
        b'{"iv":0.20000000000000004,"runtime":"A"}',
        b'{"iv":0.2,"runtime":"B"}',
        original + b"\n",
    ):
        value = observation.compare_iv_stage_observations(
            original,
            changed,
            b"artifact",
            b"artifact",
            recorded_before_sha256=digest(original),
            recorded_after_sha256=digest(original),
            expected_bundle_id=digest(b"artifact"),
        )
        assert not value.all_observations_match
        assert not value.second_matches_recorded_digest


def test_native_and_artifact_roles_bound_into_fingerprint():
    one = compare([b"a", b"b", b"c", b"d"])
    two = compare([b"b", b"a", b"d", b"c"])
    assert one.evidence_fingerprint != two.evidence_fingerprint
    assert one.first_native_sha256 == two.second_native_sha256
    assert one.first_artifact_sha256 == two.second_artifact_sha256


def test_arbitrary_equal_bytes_are_not_a_native_schema_or_authority_check():
    raw = b"invalid JSON, not a native result"
    value = observation.compare_iv_stage_observations(
        raw,
        raw,
        raw,
        raw,
        recorded_before_sha256=digest(raw),
        recorded_after_sha256=digest(raw),
        expected_bundle_id=digest(raw),
    )
    assert value.all_observations_match
    assert not any(
        field.name in ("publication_asserted", "decision_eligibility_asserted")
        for field in fields(value)
    )


def test_native_consumer_import_default_denials_and_no_caller_dto_parameters():
    import inspect

    from nse_quant.data_platform import research_iv_stage_revalidation as consumer

    params = inspect.signature(consumer.revalidate_research_iv_first_stage).parameters
    assert "requests" not in params and "bundle" not in params and "result" not in params
    assert params["expected_stage_fingerprint"].default is inspect.Parameter.empty
    defaults = {field.name: field.default for field in fields(consumer.ResearchIvCurrentStage)}
    for key in (
        "publication_asserted",
        "decision_eligibility_asserted",
        "current_source_checked",
        "archived_stage_recording_verified",
        "recorded_native_digests_matched",
        "artifact_bytes_matched",
        "stage_unchanged_observed",
    ):
        assert defaults[key] is False
    assert defaults["bundle_id"] is None and defaults["evidence_fingerprint"] is None
    assert defaults["canonical_contract_id"] is None
