"""Canonical content tests and reader-boundary assembly tests; no publication."""

import json
from dataclasses import asdict, replace

import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import quote_bundle_assembly as assembly
from nse_quant.data_platform.gold_quote_features import (
    ExactPriceFeature,
    GoldQuoteCandidate,
)
from nse_quant.data_platform.gold_quote_reader import GoldQuoteEvidence


def candidate(seed=1):
    value = GoldQuoteCandidate(
        "",
        codec.FEATURE_VERSION,
        "d" * 64,
        f"{seed:064x}",
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        source_evidence_fingerprint="a" * 64,
        source_association_fingerprint="b" * 64,
        source_frame_revision_id=f"{seed + 100:064x}",
        source_packet_ordinal=0,
        reference_assessment_revision_id="c" * 64,
        reference_row_ordinal=0,
        reference_source_fields_hash="e" * 64,
        provider_token=257,
        price_divisor=100,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
        quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
    )
    return replace(value, build_id=codec.digest(codec.canonical(asdict(value)).encode()))


def member(seed=1):
    value = candidate(seed)
    encoded = codec.canonical(asdict(value))
    return codec.QuoteBundleMember(
        value.build_id,
        codec.GOLD_READER_VERSION,
        "f" * 64,
        ("job-1",),
        codec.digest(encoded.encode()),
        encoded,
    )


def evidence(seed=1):
    value = candidate(seed)
    return GoldQuoteEvidence(
        codec.GOLD_READER_VERSION,
        value.build_id,
        "verified_current",
        "SOURCE_RECOMPUTED",
        (value.build_id,),
        ("job-1",),
        value,
        "f" * 64,
    )


def modify_candidate(item, change):
    value = json.loads(item.candidate_json)
    change(value)
    value["build_id"] = ""
    value["build_id"] = codec.digest(codec.canonical(value).encode())
    encoded = codec.canonical(value)
    return replace(
        item,
        build_id=value["build_id"],
        candidate_sha256=codec.digest(encoded.encode()),
        candidate_json=encoded,
    )


def test_roundtrip_identity_is_hash_of_exact_manifest_bytes():
    bundle = codec.make_quote_bundle((member(),))
    raw = codec.encode_quote_bundle(bundle)
    assert codec.digest(raw) == bundle.bundle_id
    assert codec.decode_quote_bundle(raw, expected_bundle_id=bundle.bundle_id) == bundle
    assert "bundle_id" not in json.loads(raw)
    assert bundle.publication_asserted is False
    assert bundle.published_at is None
    assert bundle.historical_validity_asserted is False
    assert bundle.decision_eligibility_asserted is False
    snapshot = json.loads(bundle.members[0].candidate_json)
    assert snapshot["event_ts"] is None
    assert snapshot["features"][0]["decimal_value"] == "123.45"


def test_membership_order_does_not_change_identity():
    first, second = member(1), member(2)
    assert codec.make_quote_bundle((first, second)) == codec.make_quote_bundle((second, first))


def test_changed_evidence_changes_bundle_not_candidate_identity():
    original = member()
    changed = replace(original, evidence_fingerprint="a" * 64)
    first, second = codec.make_quote_bundle((original,)), codec.make_quote_bundle((changed,))
    assert first.bundle_id != second.bundle_id
    assert first.members[0].build_id == second.members[0].build_id


@pytest.mark.parametrize("items", [(), (member(), member()), tuple(member() for _ in range(65))])
def test_invalid_membership(items):
    with pytest.raises(ValueError):
        codec.make_quote_bundle(items)


def test_same_frame_packet_feature_not_first_or_last_wins():
    first = member(1)
    other = modify_candidate(
        member(2),
        lambda value: value.update(
            source_frame_revision_id=json.loads(first.candidate_json)["source_frame_revision_id"]
        ),
    )
    with pytest.raises(ValueError, match="DUPLICATE_BUNDLE_PACKET_FEATURE_KEY"):
        codec.make_quote_bundle((first, other))


@pytest.mark.parametrize(
    "changes",
    [
        {"gold_reader_version": "unknown"},
        {"evidence_fingerprint": "bad"},
        {"successful_attempt_job_ids": ()},
        {"successful_attempt_job_ids": ("job-1", "job-1")},
        {"successful_attempt_job_ids": ("unsafe message",)},
        {"candidate_sha256": "bad"},
        {"candidate_json": "{}"},
    ],
)
def test_invalid_member_metadata(changes):
    with pytest.raises(ValueError):
        codec.make_quote_bundle((replace(member(), **changes),))


@pytest.mark.parametrize(
    "changes",
    [
        {"decision_eligibility_asserted": True},
        {"published_at": "2026-01-01T00:00:00+00:00"},
        {"effective_from": "2026-01-01T00:00:00+00:00"},
        {"canonical_contract_id": "guessed"},
        {"status": "blocked"},
        {"price_divisor": True},
        {"provider_token": 0},
        {"source_packet_ordinal": True},
        {"reference_row_ordinal": -1},
        {"source_evidence_fingerprint": "unknown"},
        {"feature_version": "next@2"},
        {"quality_flags": []},
        {"event_ts": "2026-01-01T00:00:00"},
        {"event_ts": "2026-01-01T05:30:00+05:30"},
    ],
)
def test_invalid_or_ineligible_candidate_contract(changes):
    changed = modify_candidate(member(), lambda value: value.update(changes))
    with pytest.raises(ValueError):
        codec.make_quote_bundle((changed,))


def test_wrong_decimal_not_hidden_by_recomputed_hashes():
    def change(value):
        value["features"][0]["decimal_value"] = "123.46"

    changed = modify_candidate(member(), change)
    with pytest.raises(ValueError, match="BUNDLE_EXACT_PRICE_MISMATCH"):
        codec.make_quote_bundle((changed,))


def test_price_numerator_bool_not_integer():
    def change(value):
        value["features"][0]["numerator"] = True

    with pytest.raises(ValueError):
        codec.make_quote_bundle((modify_candidate(member(), change),))


def test_unknown_candidate_fields_require_version_review():
    changed = modify_candidate(member(), lambda value: value.update(extra="unknown"))
    with pytest.raises(ValueError, match="BUNDLE_CANDIDATE_SCHEMA_MISMATCH"):
        codec.make_quote_bundle((changed,))


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(publication_asserted=True),
        lambda value: value.update(decision_eligibility_asserted=True),
        lambda value: value.update(historical_validity_asserted=True),
        lambda value: value.update(bundle_version="unknown"),
        lambda value: value.update(membership_fingerprint="f" * 64),
        lambda value: value.update(extra="unknown"),
    ],
)
def test_manifest_tampering_with_valid_outer_hash_still_rejected(change):
    bundle = codec.make_quote_bundle((member(),))
    manifest = json.loads(codec.encode_quote_bundle(bundle))
    change(manifest)
    raw = codec.canonical(manifest).encode()
    with pytest.raises(ValueError):
        codec.decode_quote_bundle(raw, expected_bundle_id=codec.digest(raw))


@pytest.mark.parametrize("kind", ["duplicate_key", "nonfinite", "whitespace"])
def test_strict_canonical_json(kind):
    raw = codec.encode_quote_bundle(codec.make_quote_bundle((member(),)))
    if kind == "duplicate_key":
        raw = raw.replace(b'"bundle_version":', b'"bundle_version":"bad","bundle_version":', 1)
    elif kind == "nonfinite":
        raw = raw.replace(b'"published_at":null', b'"published_at":NaN')
    else:
        raw += b" "
    with pytest.raises(ValueError):
        codec.decode_quote_bundle(raw, expected_bundle_id=codec.digest(raw))


def test_checksum_limits_and_bounded_file_read(tmp_path, monkeypatch):
    bundle = codec.make_quote_bundle((member(),))
    raw = codec.encode_quote_bundle(bundle)
    with pytest.raises(ValueError, match="BUNDLE_CHECKSUM_MISMATCH"):
        codec.decode_quote_bundle(raw + b"x", expected_bundle_id=bundle.bundle_id)
    target = tmp_path / (bundle.bundle_id + ".json")
    target.write_bytes(raw)
    before = target.read_bytes()
    assert codec.read_quote_bundle_file(tmp_path, bundle_id=bundle.bundle_id) == bundle
    assert target.read_bytes() == before
    monkeypatch.setattr(codec, "MAX_BUNDLE_BYTES", len(raw) - 1)
    with pytest.raises(ValueError):
        codec.read_quote_bundle_file(tmp_path, bundle_id=bundle.bundle_id)
    with pytest.raises(ValueError, match="EXACT_BUNDLE_PIN_REQUIRED"):
        codec.read_quote_bundle_file(tmp_path, bundle_id="../outside")


def test_member_size_bound(monkeypatch):
    monkeypatch.setattr(codec, "MAX_MEMBER_BYTES", 1)
    with pytest.raises(ValueError):
        codec.make_quote_bundle((member(),))


def test_assembly_two_passes_exact_pins_and_deterministic_membership(monkeypatch):
    sources = [object() for _ in range(5)]
    states = {evidence(seed).build_id: evidence(seed) for seed in (1, 2)}
    calls = []

    def read(*connections, build_id):
        assert list(connections) == sources
        calls.append(build_id)
        return states[build_id]

    monkeypatch.setattr(assembly, "read_quote_price_build", read)
    pins = tuple(reversed(sorted(states)))
    bundle = assembly.assemble_quote_bundle(*sources, build_ids=pins)
    assert calls == sorted(states) + sorted(states)
    assert bundle == codec.make_quote_bundle((member(1), member(2)))


@pytest.mark.parametrize("case", ["reader_blocked", "domain_blocked", "wrong_pin", "missing_hash"])
def test_assembly_rejects_any_member_without_partial_result(monkeypatch, case):
    value = evidence()
    if case == "reader_blocked":
        value = replace(value, status="blocked", candidate=None)
    elif case == "domain_blocked":
        value = replace(value, candidate=replace(value.candidate, status="blocked"))
    elif case == "wrong_pin":
        value = replace(value, build_id="f" * 64)
    else:
        value = replace(value, evidence_fingerprint=None)
    monkeypatch.setattr(assembly, "read_quote_price_build", lambda *a, **kw: value)
    with pytest.raises(assembly.BundleAssemblyRejected):
        assembly.assemble_quote_bundle(
            None, None, None, None, None, build_ids=(evidence().build_id,)
        )


def test_second_pass_detects_drift_without_retry(monkeypatch):
    initial = evidence()
    sequence = iter((initial, replace(initial, evidence_fingerprint="a" * 64)))
    calls = []

    def read(*args, **kwargs):
        calls.append(1)
        return next(sequence)

    monkeypatch.setattr(assembly, "read_quote_price_build", read)
    with pytest.raises(assembly.BundleAssemblyRejected, match="CHANGED_DURING_ASSEMBLY"):
        assembly.assemble_quote_bundle(None, None, None, None, None, build_ids=(initial.build_id,))
    assert calls == [1, 1]


@pytest.mark.parametrize("pins", [(), ("bad",), ("a" * 64, "a" * 64), ["a" * 64]])
def test_invalid_pins_do_not_call_reader(monkeypatch, pins):
    def fail(*args, **kwargs):
        raise AssertionError("Reader should not run")

    monkeypatch.setattr(assembly, "read_quote_price_build", fail)
    with pytest.raises(ValueError):
        assembly.assemble_quote_bundle(None, None, None, None, None, build_ids=pins)


def test_reader_execution_errors_propagate(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("operational failure")

    monkeypatch.setattr(assembly, "read_quote_price_build", fail)
    with pytest.raises(RuntimeError, match="operational failure"):
        assembly.assemble_quote_bundle(
            None, None, None, None, None, build_ids=(evidence().build_id,)
        )


def test_negative_range_and_quality_are_preserved_exactly():
    def change(value):
        values = [
            ("last_price", 12345),
            ("open", 12000),
            ("high", 11999),
            ("low", 12000),
            ("close", 12000),
            ("intra_packet_range", -1),
        ]
        value["features"] = [
            {
                "name": name,
                "numerator": number,
                "denominator": 100,
                "decimal_value": "-0.01" if number == -1 else f"{number // 100}.{number % 100:02d}",
            }
            for name, number in values
        ]
        value["quality_flags"] = ["INVERTED_HIGH_LOW", "EXCHANGE_EVENT_TIME_UNKNOWN"]

    bundle = codec.make_quote_bundle((modify_candidate(member(), change),))
    decoded = codec.decode_quote_bundle(
        codec.encode_quote_bundle(bundle), expected_bundle_id=bundle.bundle_id
    )
    assert json.loads(decoded.members[0].candidate_json)["features"][-1]["decimal_value"] == "-0.01"


def test_zero_price_is_not_fabricated_as_missing():
    def change(value):
        value["features"][0].update(numerator=0, decimal_value="0.00")
        value["quality_flags"] = ["ZERO_LAST_PRICE", "EXCHANGE_EVENT_TIME_UNKNOWN"]

    bundle = codec.make_quote_bundle((modify_candidate(member(), change),))
    assert json.loads(bundle.members[0].candidate_json)["features"][0]["numerator"] == 0


@pytest.mark.parametrize(
    "segment,divisor,expected",
    [
        (1, 100, "42949672.95"),
        (6, 10_000, "429496.7295"),
        (3, 10_000_000, "429.4967295"),
    ],
)
def test_exact_provider_scales_at_unsigned_extreme(segment, divisor, expected):
    def change(value):
        value["provider_token"] = 256 + segment
        value["price_divisor"] = divisor
        value["features"][0].update(
            numerator=2**32 - 1, denominator=divisor, decimal_value=expected
        )

    bundle = codec.make_quote_bundle((modify_candidate(member(), change),))
    assert json.loads(bundle.members[0].candidate_json)["features"][0]["decimal_value"] == expected


def test_total_bundle_limit_prevents_output(monkeypatch):
    monkeypatch.setattr(codec, "MAX_BUNDLE_BYTES", 1)
    with pytest.raises(ValueError, match="BUNDLE_BYTE_LIMIT"):
        codec.make_quote_bundle((member(),))


def test_exact_max_members_and_immutable_snapshot():
    members = tuple(member(seed) for seed in range(1, 65))
    bundle = codec.make_quote_bundle(members)
    assert len(bundle.members) == 64
    external = json.loads(bundle.members[0].candidate_json)
    external["features"][0]["decimal_value"] = "changed"
    assert "changed" not in codec.encode_quote_bundle(bundle).decode()
