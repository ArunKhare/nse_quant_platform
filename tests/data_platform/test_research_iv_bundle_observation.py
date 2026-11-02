"""Pure byte fixtures: never simulated successful native math or native integration."""

from dataclasses import asdict
from itertools import product
from typing import cast

import pytest

from nse_quant.data_platform import research_iv_bundle_observation as observation


@pytest.mark.parametrize(
    "symbols",
    list(product((b"synthetic-A", b"synthetic-B"), repeat=3)),
    ids=["aaa", "aab", "aba", "abb", "baa", "bab", "bba", "bbb"],
)
def test_every_pairwise_equality_and_negative_observation(symbols):
    recorded, first, second = symbols
    value = observation.compare_iv_bundle_observations(recorded, first, second)
    assert value.recorded_matches_first is (recorded == first)
    assert value.recorded_matches_second is (recorded == second)
    assert value.fresh_observations_match is (first == second)
    assert value.all_observations_match is (recorded == first == second)
    assert len(value.reason_codes) == sum((recorded != first, recorded != second, first != second))
    assert value == observation.compare_iv_bundle_observations(recorded, first, second)


@pytest.mark.parametrize("position", range(3), ids=["recorded", "first", "second"])
@pytest.mark.parametrize(
    "bad", [b"", bytearray(b"x"), "x", None, 1], ids=["empty", "mutable", "str", "none", "int"]
)
def test_exact_immutable_bytes_in_every_role(position, bad):
    items = [b"synthetic"] * 3
    items[position] = cast(bytes, bad)
    with pytest.raises(ValueError, match="BOUNDED_IMMUTABLE"):
        observation.compare_iv_bundle_observations(*items)


def test_size_boundary_checked_before_comparison(monkeypatch):
    monkeypatch.setattr(observation, "MAX_OBSERVATION_BYTES", 4)
    value = observation.compare_iv_bundle_observations(b"xxxx", b"xxxx", b"xxxx")
    assert value.all_observations_match
    for index in range(3):
        items = [b"xxxx"] * 3
        items[index] = b"xxxxx"
        with pytest.raises(ValueError):
            observation.compare_iv_bundle_observations(*items)


def test_never_parse_normalize_round_or_ignore_metadata():
    recorded = b'{"iv":0.2,"runtime":"synthetic-A"}'
    for changed in (
        b'{"iv":0.20000000000000004,"runtime":"synthetic-A"}',
        b'{"iv":0.2,"runtime":"synthetic-B"}',
        b'{ "iv":0.2,"runtime":"synthetic-A"}',
        recorded + b"\n",
    ):
        value = observation.compare_iv_bundle_observations(recorded, changed, recorded)
        assert not value.all_observations_match
        assert value.recorded_matches_second
        assert not value.recorded_matches_first
        assert not value.fresh_observations_match


def test_later_good_never_replaces_earlier_bad():
    value = observation.compare_iv_bundle_observations(b"recorded", b"negative", b"recorded")
    assert not value.all_observations_match
    assert value.reason_codes == (
        "FIRST_CURRENT_IV_BUNDLE_DIFFERS_FROM_RECORDING",
        "CURRENT_IV_BUNDLE_OBSERVATIONS_DIFFER",
    )


def test_unchanged_later_pair_does_not_reproduce_recording():
    value = observation.compare_iv_bundle_observations(b"old", b"new", b"new")
    assert value.fresh_observations_match
    assert not value.all_observations_match
    assert len(value.reason_codes) == 2


def test_fingerprint_binds_all_roles_and_contains_no_authority_claim():
    one = observation.compare_iv_bundle_observations(b"one", b"two", b"three")
    two = observation.compare_iv_bundle_observations(b"one", b"three", b"two")
    assert one.evidence_fingerprint != two.evidence_fingerprint
    assert one.first_sha256 == two.second_sha256
    assert one.second_sha256 == two.first_sha256
    assert len(one.evidence_fingerprint) == 64
    fields = asdict(one)
    assert "decision_eligibility_asserted" not in fields
    assert "current_source_checked" not in fields
    assert "publication_asserted" not in fields


def test_repeated_incorrect_byte_strings_are_only_byte_equality():
    invalid_document = b"not JSON, not IV, not a native assembly"
    value = observation.compare_iv_bundle_observations(
        invalid_document,
        invalid_document,
        invalid_document,
    )
    assert value.all_observations_match
    assert value.version == "research-iv-bundle-observation@1"


def test_service_import_is_lazy_and_default_report_grants_nothing():
    import inspect

    from nse_quant.data_platform import research_iv_bundle_revalidation as service

    value = service.ResearchIvBundleRevalidation(
        service.VERSION,
        "a" * 64,
        "b" * 64,
        "review_required",
        ("SYNTHETIC_ONLY",),
    )
    for key, item in asdict(value).items():
        if key.endswith(("_asserted", "_verified", "_checked", "_reproduced", "_observed")):
            assert item is False
    assert value.all_members_revalidated is False
    assert value.bundle_id is None and value.evidence_fingerprint is None
    parameters = inspect.signature(service.revalidate_research_iv_bundle).parameters
    assert set(parameters) == {
        "bronze",
        "frame_silver",
        "reference_silver",
        "assessments",
        "source_gold",
        "archive",
        "bundle_archive",
        "build_id_pin",
        "expected_archive_fingerprint",
    }
    assert parameters["expected_archive_fingerprint"].default is inspect.Parameter.empty
    assert "requests" not in parameters and "bundle" not in parameters


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "wrong-archive-hash",
        "extra",
        "missing",
        "wrong-payload-hash",
        "duplicate-manifest-entry",
        "empty-payload",
        "trailing-whitespace",
        "bad-crc",
    ],
    ids=[
        "valid",
        "archive-hash",
        "extra",
        "missing",
        "payload-hash",
        "duplicate",
        "empty",
        "space",
        "crc",
    ],
)
def test_zip_verifier_with_synthetic_archives(tmp_path, mutation):
    import hashlib
    import runpy
    from pathlib import Path
    from zipfile import BadZipFile, ZipFile

    verifier = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "scripts/qa/verify_research_iv_bundle_revalidation_patch.py"
        )
    )
    payloads = {name: (name + "\n").encode() for name in verifier["PAYLOADS"]}
    ordered = sorted(payloads)
    manifest = "".join(
        hashlib.sha256(payloads[name]).hexdigest() + "  " + name + "\n" for name in ordered
    )
    if mutation == "wrong-payload-hash":
        payloads[ordered[0]] = b"changed\n"
    elif mutation == "extra":
        payloads["extra.txt"] = b"extra\n"
    elif mutation == "missing":
        del payloads[ordered[0]]
    elif mutation == "duplicate-manifest-entry":
        manifest += manifest.splitlines()[0] + "\n"
    elif mutation in ("empty-payload", "trailing-whitespace"):
        payloads[ordered[0]] = b"" if mutation == "empty-payload" else b"space \n"
        manifest = "".join(
            hashlib.sha256(payloads[name]).hexdigest() + "  " + name + "\n" for name in ordered
        )
    archive = tmp_path / "synthetic.zip"
    with ZipFile(archive, "w") as bundle:
        for name, raw in payloads.items():
            bundle.writestr(name, raw)
        bundle.writestr(verifier["MANIFEST"], manifest)
    if mutation == "bad-crc":
        raw = archive.read_bytes()
        marker = payloads[ordered[0]]
        offset = raw.index(marker)
        archive.write_bytes(raw[:offset] + bytes([raw[offset] ^ 1]) + raw[offset + 1 :])
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    if mutation == "wrong-archive-hash":
        checksum = "0" * 64
    if mutation == "none":
        verifier["verify"](archive, checksum)
    else:
        with pytest.raises((ValueError, BadZipFile)):
            verifier["verify"](archive, checksum)
