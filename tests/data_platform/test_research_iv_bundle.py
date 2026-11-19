"""Synthetic artifact consistency fixtures, NOT actual math/source/audit verification."""

import json
from dataclasses import replace

import pytest

from nse_quant.data_platform import research_iv_bundle as codec


def synthetic_member(index=1, **changes):
    terms = dict(
        strike=str(100 + index),
        annual_rate="0.05",
        annual_dividend_yield="0.02",
        assumed_years_to_expiry="1",
        option_type="CE",
    )
    terms_pin = codec.sha(codec.canonical([codec.MODEL_VERSION, terms]).encode())
    definition = "d" * 64
    option, spot = "a" * 64, "b" * 64
    group = codec.sha(
        codec.canonical(
            [
                "research-iv-build-record@1",
                option,
                spot,
                terms_pin,
                definition,
            ]
        ).encode()
    )
    # Deliberately only a self-consistent document: hashes do not prove model truth.
    calculation = dict(
        calculation_id="",
        model_version=codec.MODEL_VERSION,
        status="computed_research_scenario",
        reason_codes=["EXPLICIT_EUROPEAN_BSM_SCENARIO_SOLVED"],
        input_fingerprint="c" * 64,
        scipy_version="1.14.0",
        python_version="3.12.0",
        implied_volatility=0.2,
        greeks=dict(
            price=1.0,
            delta=0.5,
            gamma=0.1,
            vega_per_vol_unit=1.0,
            theta_per_calendar_day=-0.1,
            rho_per_rate_unit=1.0,
        ),
        price_residual=0.0,
        canonical_contract_id=None,
        model_suitability_verified=False,
        underlying_identity_verified=False,
        source_acquisition_authenticity_asserted=False,
        availability_evidence_verified=False,
        historical_validity_asserted=False,
        publication_asserted=False,
        decision_eligibility_asserted=False,
    )
    calculation["calculation_id"] = codec.sha(codec.canonical(calculation).encode())
    member = codec.IvBundleMember(
        f"{index:064x}",
        group,
        definition,
        "e" * 64,
        "f" * 64,
        option,
        spot,
        terms_pin,
        codec.canonical(calculation),
        codec.canonical(terms),
    )
    return replace(member, **changes)


def modify_calculation(member, **changes):
    value = json.loads(member.calculation_json)
    value.update(changes)
    value["calculation_id"] = ""
    value["calculation_id"] = codec.sha(codec.canonical(value).encode())
    return replace(member, calculation_json=codec.canonical(value))


def test_deterministic_roundtrip_and_no_trust_flags():
    first, second = synthetic_member(1), synthetic_member(2)
    bundle = codec.make_research_iv_bundle((second, first))
    assert bundle == codec.make_research_iv_bundle((first, second))
    assert bundle.members == (first, second)
    raw = codec.encode_research_iv_bundle(bundle)
    assert codec.decode_research_iv_bundle(raw, expected_bundle_id=bundle.bundle_id) == bundle
    assert bundle.published_at is None
    assert not bundle.publication_asserted
    assert not bundle.availability_evidence_verified
    assert not bundle.historical_validity_asserted
    assert not bundle.option_underlying_identity_binding_verified
    assert not bundle.decision_eligibility_asserted
    assert bundle.canonical_contract_id is None


def test_same_scenario_not_counted_twice_under_different_builds():
    one = synthetic_member()
    with pytest.raises(ValueError, match="DUPLICATE_EXACT_SCENARIO"):
        codec.make_research_iv_bundle((one, replace(one, build_id="9" * 64)))


@pytest.mark.parametrize(
    "field",
    [
        "build_id",
        "input_id",
        "definition_fingerprint",
        "archive_fingerprint",
        "revalidation_fingerprint",
        "option_build_id",
        "spot_build_id",
        "scenario_terms_sha256",
    ],
)
def test_all_member_pins_required(field):
    with pytest.raises(ValueError):
        codec.make_research_iv_bundle((replace(synthetic_member(), **{field: "bad"}),))


@pytest.mark.parametrize(
    "change",
    [
        {"model_suitability_verified": True},
        {"decision_eligibility_asserted": True},
        {"publication_asserted": True},
        {"canonical_contract_id": "invented"},
        {"model_version": "unknown@2"},
        {"status": "review_required"},
        {"implied_volatility": True},
        {"implied_volatility": 5.1},
        {"price_residual": None},
        {"extra": True},
    ],
    ids=[
        "suitability",
        "eligible",
        "published",
        "canonical",
        "version",
        "review",
        "bool-vol",
        "vol-bound",
        "no-residual",
        "extra",
    ],
)
def test_self_rehashed_calculation_cannot_escalate_contract(change):
    bad = modify_calculation(synthetic_member(), **change)
    with pytest.raises(ValueError):
        codec.make_research_iv_bundle((bad,))


def test_unchecked_calculation_hash_change_rejected():
    member = synthetic_member()
    raw = member.calculation_json.replace('"implied_volatility":0.2', '"implied_volatility":0.3')
    with pytest.raises(ValueError, match="CALCULATION_IDENTITY"):
        codec.make_research_iv_bundle((replace(member, calculation_json=raw),))


@pytest.mark.parametrize("clock", ["2026-01-01T00:00:00", "2026-01-01T05:30:00+05:30", True])
def test_source_clocks_not_replaced_or_relabelled(clock):
    with pytest.raises(ValueError):
        codec.make_research_iv_bundle((synthetic_member(source_option_event_ts=clock),))


def test_known_utc_and_unknown_clocks_preserved():
    member = synthetic_member(source_option_event_ts="2026-01-01T00:00:00+00:00")
    bundle = codec.make_research_iv_bundle((member,))
    assert bundle.members[0].source_spot_event_ts is None
    assert bundle.members[0].source_option_event_ts == member.source_option_event_ts


def test_strict_manifest_duplicate_fields_unknowns_and_trailing_bytes():
    bundle = codec.make_research_iv_bundle((synthetic_member(),))
    raw = codec.encode_research_iv_bundle(bundle)
    variants = [
        raw + b"\n",
        raw + b"{}",
        b" " + raw,
        raw.replace(b'"version":', b'"version":"bad","version":', 1),
    ]
    decoded = json.loads(raw)
    decoded["unknown"] = True
    variants.append(codec.canonical(decoded).encode())
    for value in variants:
        with pytest.raises(ValueError):
            codec.decode_research_iv_bundle(value, expected_bundle_id=codec.sha(value))


def test_wrong_bundle_pin_and_membership_pin_rejected():
    bundle = codec.make_research_iv_bundle((synthetic_member(),))
    raw = codec.encode_research_iv_bundle(bundle)
    with pytest.raises(ValueError, match="CHECKSUM"):
        codec.decode_research_iv_bundle(raw, expected_bundle_id="0" * 64)
    with pytest.raises(ValueError, match="MEMBERSHIP"):
        codec.encode_research_iv_bundle(replace(bundle, membership_fingerprint="0" * 64))


@pytest.mark.parametrize(
    "field,value",
    [
        ("publication_asserted", True),
        ("decision_eligibility_asserted", True),
        ("published_at", "invented"),
        ("evidence_mode", "PUBLISHED"),
    ],
)
def test_no_bundle_policy_upgrade(field, value):
    bundle = codec.make_research_iv_bundle((synthetic_member(),))
    with pytest.raises(ValueError):
        codec.encode_research_iv_bundle(replace(bundle, **{field: value}))


def test_count_limits_and_mutability():
    for members in ((), [synthetic_member()], tuple(synthetic_member(i + 1) for i in range(65))):
        with pytest.raises(ValueError):
            codec.make_research_iv_bundle(members)
    with pytest.raises(ValueError):
        codec.decode_research_iv_bundle(bytearray(b"x"), expected_bundle_id="0" * 64)


def test_no_mixed_numerical_runtime():
    one, two = synthetic_member(1), modify_calculation(synthetic_member(2), python_version="3.14.2")
    with pytest.raises(ValueError, match="MIXED_NUMERICAL"):
        codec.make_research_iv_bundle((one, two))


def test_member_byte_limit_no_prefix_salvage():
    with pytest.raises(ValueError, match="MEMBER_BYTE_LIMIT"):
        codec.make_research_iv_bundle((synthetic_member(terms_json="x" * 16385),))


def test_no_mixed_definition_even_with_distinct_scenarios():
    one, two = synthetic_member(1), synthetic_member(2)
    changed = replace(two, definition_fingerprint="9" * 64)
    group = codec.sha(
        codec.canonical(
            [
                "research-iv-build-record@1",
                changed.option_build_id,
                changed.spot_build_id,
                changed.scenario_terms_sha256,
                changed.definition_fingerprint,
            ]
        ).encode()
    )
    changed = replace(changed, input_id=group)
    with pytest.raises(ValueError, match="MIXED_MODEL_DEFINITIONS"):
        codec.make_research_iv_bundle((one, changed))


def test_no_bool_greek_or_nonfinite_json_prefix_salvage():
    original = synthetic_member()
    value = json.loads(original.calculation_json)
    value["greeks"]["gamma"] = True
    bad = modify_calculation(original, greeks=value["greeks"])
    with pytest.raises(ValueError, match="FINITE_GREEKS"):
        codec.make_research_iv_bundle((bad,))
    malformed = original.calculation_json.replace(
        '"implied_volatility":0.2', '"implied_volatility":NaN'
    )
    with pytest.raises(ValueError):
        codec.make_research_iv_bundle((replace(original, calculation_json=malformed),))
