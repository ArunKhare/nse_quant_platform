"""Actual Gold SQL reader integration with its existing SOURCE KERNEL substituted.

Not native Bronze-to-analytics E2E. Uses existing documented Gold reader fixture.
"""

from dataclasses import asdict, replace

import pytest
from test_gold_quote_reader import candidate, digest
from test_gold_quote_reader import setup as setup

from nse_quant.data_platform import gold_quote_reader as gold_reader
from nse_quant.data_platform import native_research_option as service
from nse_quant.data_platform.gold_quote_features import (
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    ExactPriceFeature,
)
from nse_quant.data_platform.gold_quote_store import STORE_VERSION
from nse_quant.data_platform.research_option_model import ScenarioTerms, scenario_terms_sha256


@pytest.fixture
def scenario(setup, monkeypatch):
    sources, gold, state, _, insert, group = setup
    old = candidate()
    option = replace(old, build_id="", price_divisor=100)
    option = replace(option, build_id=digest(asdict(option)))
    insert(option, links=(old.build_id,), job="option-job", group_id=group)
    spot = replace(
        option,
        build_id="",
        source_assessment_revision_id="e" * 64,
        features=(ExactPriceFeature("last_price", 100000, 100, "1000.00"),),
    )
    spot = replace(spot, build_id=digest(asdict(spot)))
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    spot_group = digest([spot.source_assessment_revision_id, versions])
    insert(spot, job="spot-job", group_id=spot_group)
    current = {
        option.source_assessment_revision_id: option,
        spot.source_assessment_revision_id: spot,
    }

    def substituted_source(*connections, assessment_revision_id):
        assert list(connections) == sources
        return current[assessment_revision_id]

    monkeypatch.setattr(gold_reader, "build_quote_price_candidate", substituted_source)
    terms = ScenarioTerms("1000", "0.05", "0.02", "1", "CE")
    arguments = dict(
        option_build_id=option.build_id,
        spot_build_id=spot.build_id,
        terms=terms,
        expected_scenario_terms_sha256=scenario_terms_sha256(terms),
    )

    def run(**changes):
        return service.build_native_research_iv_candidate(
            *sources, gold, **dict(arguments, **changes)
        )

    return run, current, option, spot, gold, state


def test_two_actual_gold_reads_and_unknown_times_preserved(scenario):
    run, _, _, _, _, _ = scenario
    value = run()
    assert value.status == "research_iv_candidate"
    assert value.native_price_inputs_rechecked
    assert value.calculation.implied_volatility > 0
    assert value.source_option_event_ts is None
    assert value.source_spot_event_ts is None
    assert not value.scenario_terms_authoritative
    assert not value.option_underlying_identity_binding_verified
    assert not value.publication_asserted
    assert not value.historical_validity_asserted
    assert not value.availability_evidence_verified
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.canonical_contract_id is None
    assert value.evidence_fingerprint == run().evidence_fingerprint


def test_explicit_scenario_pin_required_before_reads(scenario):
    run, _, _, _, _, _ = scenario
    with pytest.raises(ValueError, match="TERMS_PIN_MISMATCH"):
        run(expected_scenario_terms_sha256="0" * 64)


def test_same_source_pin_cannot_fill_both_roles(scenario):
    run, _, option, _, _, _ = scenario
    with pytest.raises(ValueError, match="TWO_DISTINCT"):
        run(spot_build_id=option.build_id)


def test_gold_invalidation_blocks_without_old_good_fallback(scenario):
    run, current, option, _, _, _ = scenario
    current[option.source_assessment_revision_id] = replace(option, status="blocked")
    value = run()
    assert value.status == "review_required"
    assert not value.native_price_inputs_rechecked
    assert value.calculation is None


def test_actual_gold_reader_calls_detect_drift(scenario, monkeypatch):
    run, current, option, _, _, _ = scenario
    real = gold_reader.read_quote_price_build
    calls = 0

    def observe(*connections, **kwargs):
        nonlocal calls
        value = real(*connections, **kwargs)
        calls += 1
        if calls == 2:
            current[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(gold_reader, "read_quote_price_build", observe)
    value = run()
    assert value.reason_codes == ("NATIVE_RESEARCH_PRICE_OBSERVATION_DRIFT",)
    assert value.calculation is not None
    assert not value.native_price_inputs_rechecked


def test_source_exception_not_fabricated_numeric_success(scenario, monkeypatch):
    run, _, _, _, _, _ = scenario

    def fail(*connections, **kwargs):
        raise RuntimeError("SYNTHETIC_GOLD_FAILURE")

    monkeypatch.setattr(gold_reader, "read_quote_price_build", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_GOLD_FAILURE"):
        run()
