"""Native capture/policy/reader tests with only publication-reader boundary substituted.

Not full native source-to-decision end-to-end verification.
"""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone

import duckdb
import pytest

from nse_quant.data_platform import admission_capture as capture
from nse_quant.data_platform import admission_capture_reader as archive
from nse_quant.data_platform import admission_revalidation as service
from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate
from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence

T = datetime(2026, 1, 1, tzinfo=UTC)


def evidence():
    candidate = GoldQuoteCandidate(
        "",
        codec.FEATURE_VERSION,
        "a" * 64,
        "b" * 64,
        "candidate",
        "EXACT_PROVIDER_PRICE_FIELDS",
        source_evidence_fingerprint="c" * 64,
        source_association_fingerprint="d" * 64,
        source_frame_revision_id="e" * 64,
        source_packet_ordinal=0,
        reference_assessment_revision_id="f" * 64,
        reference_row_ordinal=0,
        reference_source_fields_hash="a" * 64,
        provider_token=257,
        price_divisor=100,
        features=(ExactPriceFeature("last_price", 12345, 100, "123.45"),),
        quality_flags=("EXCHANGE_EVENT_TIME_UNKNOWN",),
    )
    build_id = codec.digest(codec.canonical(asdict(candidate)).encode())
    candidate = replace(candidate, build_id=build_id)
    raw = codec.canonical(asdict(candidate))
    bundle = codec.make_quote_bundle(
        (
            codec.QuoteBundleMember(
                build_id,
                codec.GOLD_READER_VERSION,
                "a" * 64,
                ("gold-job",),
                codec.digest(raw.encode()),
                raw,
            ),
        )
    )
    publication_id = codec.digest(
        codec.canonical(
            [
                ["research-quote-publication@1", "research-only-publication-policy@1"],
                bundle.bundle_id,
                "RESEARCH_ONLY",
            ]
        ).encode()
    )
    return ResearchPublicationEvidence(
        "research-quote-publication-consumer@1",
        publication_id,
        "verified_research_snapshot",
        "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED",
        "RESEARCH_ONLY",
        bundle.bundle_id,
        T.isoformat(),
        T.isoformat(),
        "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY",
        ("publication-job",),
        bundle,
        "e" * 64,
        True,
    )


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    source_path = tmp_path / "source.duckdb"
    with duckdb.connect(str(source_path)) as conn:
        conn.execute("CREATE TABLE marker(id INTEGER)")
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(tmp_path / "decision_inputs.duckdb"))
    state = {"evidence": evidence(), "calls": 0}

    def read(conn, *, publication_id):
        assert conn is source
        assert publication_id == state["evidence"].publication_id
        state["calls"] += 1
        return state["evidence"]

    monkeypatch.setattr(policy, "read_research_publication", read)

    def persist(request=None):
        return capture.capture_publication_admission(
            source,
            target,
            publication_id=state["evidence"].publication_id,
            request=request or policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
            actor_id="test",
            code_revision="5092b2f",
            initialize=True,
        )

    def run(pin, request=None, **kwargs):
        return service.revalidate_captured_publication_use(
            source,
            target,
            receipt_id=pin,
            publication_id=kwargs.get("publication_id", state["evidence"].publication_id),
            request=request or policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
        )

    yield source, target, state, persist, run
    source.close()
    target.close()


def test_exact_research_match_is_not_authority_and_does_not_write(inputs):
    _, target, state, persist, run = inputs
    first = persist()
    attempts = archive._name(target, "decision_inputs", "admission_attempts")
    before = target.execute(f"SELECT count(*) FROM {attempts}").fetchone()
    result = run(first["receipt_id"])
    assert result.status == "matched_research_input"
    assert result.current_request_checked
    assert result.observed_inputs_match
    assert result.research_policy_satisfied
    assert result.fresh_receipt_id == first["receipt_id"]
    assert result.evidence_fingerprint == run(first["receipt_id"]).evidence_fingerprint
    assert not result.research_analysis_authorized
    assert not result.decision_eligibility_asserted
    assert not result.availability_evidence_verified
    assert not result.economic_validity_verified
    assert not result.source_current_checked
    assert not result.replay_authenticity_asserted
    assert not result.atomic_cross_database_snapshot_asserted
    assert state["calls"] == 5
    assert target.execute(f"SELECT count(*) FROM {attempts}").fetchone() == before


def test_research_only_point_in_time_remains_rejected(inputs):
    _, _, _, persist, run = inputs
    request = policy.AdmissionRequest(policy.POINT_IN_TIME, T, T)
    first = persist(request)
    local = T.astimezone(timezone(timedelta(hours=5, minutes=30)))
    result = run(first["receipt_id"], policy.AdmissionRequest(policy.POINT_IN_TIME, local, local))
    assert result.status == "rejected"
    assert result.observed_inputs_match
    assert result.current_request_checked
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in result.reason_codes
    assert not result.research_policy_satisfied
    assert not result.decision_eligibility_asserted


def test_request_and_publication_must_match_exact_capture(inputs):
    _, _, state, persist, run = inputs
    first = persist()
    before = state["calls"]
    for result in (
        run(first["receipt_id"], policy.AdmissionRequest(policy.POINT_IN_TIME, T, T)),
        run(first["receipt_id"], publication_id="f" * 64),
    ):
        assert result.status == "review_required"
        assert not result.current_request_checked
    assert state["calls"] == before


def test_changed_source_requires_explicit_new_capture(inputs):
    _, _, state, persist, run = inputs
    first = persist()
    state["evidence"] = replace(state["evidence"], evidence_fingerprint="f" * 64)
    result = run(first["receipt_id"])
    assert result.status == "review_required"
    assert result.current_request_checked
    assert not result.observed_inputs_match
    assert result.fresh_policy_status == "ACCEPTED_RESEARCH_ONLY"
    assert result.fresh_receipt_id != first["receipt_id"]
    assert not result.research_policy_satisfied


def test_old_accepted_pin_cannot_bypass_new_rejected_head(inputs):
    _, _, state, persist, run = inputs
    accepted = persist()
    original = state["evidence"]
    state["evidence"] = replace(original, status="blocked", research_publication_verified=False)
    rejected = persist()
    state["evidence"] = original
    assert persist()["receipt_id"] == accepted["receipt_id"]
    before = state["calls"]
    old = run(accepted["receipt_id"])
    assert old.status == "review_required"
    assert not old.current_request_checked
    assert state["calls"] == before
    newer = run(rejected["receipt_id"])
    assert newer.status == "review_required"
    assert newer.fresh_policy_status == "ACCEPTED_RESEARCH_ONLY"
    assert not newer.research_policy_satisfied


def test_failed_unlinked_job_blocks_before_fresh_assessment(inputs):
    from nse_quant.data_platform.audit import AuditLedger, JobState

    _, target, state, persist, run = inputs
    first = persist()
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=capture.COMMAND,
        actor_id="test",
        code_revision="test",
        scope_ref="sha256:" + first["request_revision_id"],
        config_hash="untrusted",
    )
    ledger.transition(job, JobState.FAILED, "EXECUTION_ERROR")
    before = state["calls"]
    result = run(first["receipt_id"])
    assert result.status == "review_required"
    assert not result.current_request_checked
    assert state["calls"] == before


def test_two_fresh_assessments_detect_observed_source_drift(inputs, monkeypatch):
    _, _, state, persist, run = inputs
    first = persist()
    original = policy.read_research_publication

    def read(conn, **kwargs):
        value = original(conn, **kwargs)
        state["evidence"] = replace(value, evidence_fingerprint="f" * 64)
        return value

    monkeypatch.setattr(policy, "read_research_publication", read)
    result = run(first["receipt_id"])
    assert result.status == "review_required"
    assert result.reason_codes == ("PUBLICATION_ASSESSMENT_OBSERVATION_DRIFT",)
    assert not result.research_policy_satisfied


def test_post_assessment_capture_history_change_blocks(inputs, monkeypatch):
    _, _, state, persist, run = inputs
    first = persist()
    native = policy.assess_publication_use
    calls = 0

    def assess(*args, **kwargs):
        nonlocal calls
        value = native(*args, **kwargs)
        calls += 1
        if calls == 2:
            state["evidence"] = replace(state["evidence"], evidence_fingerprint="f" * 64)
            persist()
        return value

    monkeypatch.setattr(policy, "assess_publication_use", assess)
    result = run(first["receipt_id"])
    assert result.status == "review_required"
    assert result.reason_codes == ("CAPTURE_OBSERVATION_DRIFT",)
    assert not result.research_policy_satisfied


def test_source_failure_propagates_not_business_rejection(inputs, monkeypatch):
    _, _, _, persist, run = inputs
    first = persist()

    def fail(*args, **kwargs):
        raise RuntimeError("private source failure")

    monkeypatch.setattr(policy, "read_research_publication", fail)
    with pytest.raises(RuntimeError):
        run(first["receipt_id"])


def test_same_database_and_invalid_pins_rejected(inputs):
    source, target, state, _, _ = inputs
    request = policy.AdmissionRequest(policy.ARCHIVED_RESEARCH)
    with pytest.raises(ValueError, match="SEPARATE_REVALIDATION_DATABASES_REQUIRED"):
        service.revalidate_captured_publication_use(
            source,
            source,
            receipt_id="a" * 64,
            publication_id=state["evidence"].publication_id,
            request=request,
        )
    with pytest.raises(ValueError, match="EXACT_REVALIDATION_PINS_REQUIRED"):
        service.revalidate_captured_publication_use(
            source,
            target,
            receipt_id="BAD",
            publication_id="a" * 64,
            request=request,
        )


def test_default_cli_plan_no_execution_import_or_io(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.admission_revalidation_cli import main

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.admission_revalidation"}:
            raise AssertionError("Plan imported execution dependencies")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--publication-db",
                str(tmp_path / "missing-source.duckdb"),
                "--receipt-db",
                str(tmp_path / "missing-capture.duckdb"),
                "--publication-id",
                "a" * 64,
                "--receipt-id",
                "b" * 64,
                "--use-case",
                policy.ARCHIVED_RESEARCH,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert '"PLANNED"' in capsys.readouterr().out


def test_service_accepts_readonly_capture_connection_without_writes(inputs):
    source, target, state, persist, _ = inputs
    first = persist()
    path = target.execute("PRAGMA database_list").fetchone()[2]
    target.close()
    with duckdb.connect(path, read_only=True) as captures:
        result = service.revalidate_captured_publication_use(
            source,
            captures,
            receipt_id=first["receipt_id"],
            publication_id=state["evidence"].publication_id,
            request=policy.AdmissionRequest(policy.ARCHIVED_RESEARCH),
        )
        assert result.status == "matched_research_input"
        assert result.current_request_checked
