"""Actual two-pass revalidation/audit/model/Gold SQL, lower source kernel substituted.

Not full native acquisition-to-bundle E2E; no simulated successful native result.
"""

from dataclasses import replace

import pytest
from test_gold_quote_reader import setup as setup
from test_native_research_option_boundary import scenario as scenario
from test_research_iv_revalidation_boundary import revalidation_case as revalidation_case
from test_research_iv_store_boundary import archive_case as archive_case

from nse_quant.data_platform import native_research_iv_bundle as assembly
from nse_quant.data_platform import research_iv_revalidation as current_service
from nse_quant.data_platform import research_iv_store as store
from nse_quant.data_platform.research_iv_bundle import (
    decode_research_iv_bundle,
    encode_research_iv_bundle,
)
from nse_quant.data_platform.research_option_model import ScenarioTerms


@pytest.fixture
def bundle_case(revalidation_case, archive_case):
    target, persist, current, option, _, first_receipt, _, sources, gold = revalidation_case
    terms = archive_case[4]
    alternate = ScenarioTerms(
        "1050",
        terms.annual_rate,
        terms.annual_dividend_yield,
        terms.assumed_years_to_expiry,
        terms.option_type,
    )
    second_receipt = persist(alternate)
    requests = []
    for receipt in (first_receipt, second_receipt):
        archived = store.read_research_iv_archive(target, build_id_pin=receipt["build_id"])
        requests.append(
            assembly.IvBundleRequest(
                receipt["build_id"],
                archived.evidence_fingerprint,
            )
        )

    def run(selected=None):
        return assembly.assemble_native_research_iv_bundle(
            *sources,
            gold,
            target,
            requests=tuple(requests) if selected is None else selected,
        )

    return run, tuple(requests), target, persist, current, option


def test_actual_members_whole_set_and_offline_roundtrip(bundle_case):
    run, _, target, _, _, _ = bundle_case
    attempts = store._name(target, "gold", "research_iv_attempts")
    before = target.execute(f"SELECT * FROM {attempts} ORDER BY job_id").fetchall()
    value = run()
    assert value.all_members_revalidated
    assert value.status == "assembled_current_research_iv_bundle"
    assert len(value.bundle.members) == 2
    assert len(value.first_pass) == len(value.second_pass) == 2
    raw = encode_research_iv_bundle(value.bundle)
    assert decode_research_iv_bundle(raw, expected_bundle_id=value.bundle.bundle_id) == value.bundle
    assert not value.publication_asserted
    assert not value.availability_evidence_verified
    assert not value.historical_validity_asserted
    assert not value.option_underlying_identity_binding_verified
    assert not value.decision_eligibility_asserted
    assert not value.atomic_cross_database_snapshot_asserted
    assert value.canonical_contract_id is None
    assert all(item.source_option_event_ts is None for item in value.bundle.members)
    assert all(item.source_spot_event_ts is None for item in value.bundle.members)
    assert target.execute(f"SELECT * FROM {attempts} ORDER BY job_id").fetchall() == before


def test_request_order_does_not_change_bundle_or_membership(bundle_case):
    run, requests, _, _, _, _ = bundle_case
    one, two = run(requests), run(tuple(reversed(requests)))
    assert one.bundle.bundle_id == two.bundle.bundle_id
    assert one.evidence_fingerprint == two.evidence_fingerprint


def test_duplicate_requests_rejected_before_source_io(bundle_case, monkeypatch):
    run, requests, _, _, _, _ = bundle_case

    def forbidden(*args, **kwargs):
        raise AssertionError("Duplicate request reached native service")

    monkeypatch.setattr(current_service, "revalidate_research_iv_build", forbidden)
    with pytest.raises(ValueError, match="DUPLICATE_OR_CONFLICTING"):
        run((requests[0], requests[0]))


def test_any_bad_review_pin_blocks_entire_bundle(bundle_case):
    run, requests, _, _, _, _ = bundle_case
    bad = (requests[0], replace(requests[1], expected_archive_fingerprint="0" * 64))
    value = run(bad)
    assert not value.all_members_revalidated
    assert value.bundle is None
    assert len(value.first_pass) == len(value.second_pass) == 2
    assert "IV_BUNDLE_MEMBER_NOT_COMPLETE_IN_BOTH_PASSES" in value.reason_codes


def test_source_change_after_first_whole_pass_blocks_all(bundle_case, monkeypatch):
    run, requests, _, _, source, option = bundle_case
    real = current_service.revalidate_research_iv_build
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == len(requests):
            source[option.source_assessment_revision_id] = replace(option, status="blocked")
        return value

    monkeypatch.setattr(current_service, "revalidate_research_iv_build", observe)
    value = run()
    assert value.bundle is None
    assert not value.all_members_revalidated
    assert "IV_BUNDLE_WHOLE_SET_OBSERVATION_DRIFT" in value.reason_codes


def test_earlier_bad_observation_cannot_be_replaced_by_later_good(bundle_case, monkeypatch):
    run, _, _, _, source, option = bundle_case
    source[option.source_assessment_revision_id] = replace(option, status="blocked")
    real = current_service.revalidate_research_iv_build
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == 1:
            source[option.source_assessment_revision_id] = option
        return value

    monkeypatch.setattr(current_service, "revalidate_research_iv_build", observe)
    value = run()
    assert any(item.status == "review_required" for item in value.first_pass)
    assert all(item.status == "matched_current_research_iv" for item in value.second_pass)
    assert value.bundle is None
    assert not value.all_members_revalidated


def test_exact_archive_retry_between_passes_is_not_hidden(bundle_case, monkeypatch):
    run, requests, _, persist, _, _ = bundle_case
    real = current_service.revalidate_research_iv_build
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        value = real(*args, **kwargs)
        calls += 1
        if calls == len(requests):
            persist(initialize=False)
        return value

    monkeypatch.setattr(current_service, "revalidate_research_iv_build", observe)
    value = run()
    assert value.bundle is None
    assert not value.all_members_revalidated


def test_observation_budget_never_emits_partial_bundle(bundle_case, monkeypatch):
    run, _, _, _, _, _ = bundle_case
    monkeypatch.setattr(assembly, "MAX_PASS_BYTES", 1)
    with pytest.raises(ValueError, match="PASS_BYTE_LIMIT"):
        run()
