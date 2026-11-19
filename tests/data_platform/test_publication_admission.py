"""Purpose/time boundary and frozen policy-replay tests; registry reader substituted."""

import builtins
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta, timezone

import duckdb
import pytest

from nse_quant.data_platform import feature_bundle as codec
from nse_quant.data_platform import publication_admission as admission
from nse_quant.data_platform import publication_admission_cli as cli
from nse_quant.data_platform.gold_quote_features import ExactPriceFeature, GoldQuoteCandidate
from nse_quant.data_platform.quote_publication_reader import ResearchPublicationEvidence

T = datetime(2026, 1, 1, tzinfo=UTC)


def evidence():
    value = GoldQuoteCandidate(
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
    value = replace(value, build_id=codec.digest(codec.canonical(asdict(value)).encode()))
    raw = codec.canonical(asdict(value))
    member = codec.QuoteBundleMember(
        value.build_id,
        codec.GOLD_READER_VERSION,
        "b" * 64,
        ("gold-job",),
        codec.digest(raw.encode()),
        raw,
    )
    bundle = codec.make_quote_bundle((member,))
    identity = codec.digest(
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
        identity,
        "verified_research_snapshot",
        "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED",
        "RESEARCH_ONLY",
        bundle.bundle_id,
        T.isoformat(),
        (T + timedelta(seconds=6)).isoformat(),
        "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY",
        ("pub-job",),
        bundle,
        "e" * 64,
        True,
    )


@pytest.fixture
def setup(monkeypatch):
    state = {"evidence": evidence(), "calls": 0}
    connection = object()

    def read(conn, *, publication_id):
        assert conn is connection
        assert publication_id == state["evidence"].publication_id
        state["calls"] += 1
        return state["evidence"]

    monkeypatch.setattr(admission, "read_research_publication", read)

    def run(request=None):
        return admission.assess_publication_use(
            connection,
            publication_id=state["evidence"].publication_id,
            request=(
                admission.AdmissionRequest(admission.ARCHIVED_RESEARCH)
                if request is None
                else request
            ),
        )

    return state, run


def test_archival_research_permitted_without_point_in_time_claim(setup):
    state, run = setup
    receipt = run()
    assert receipt.status == "ACCEPTED_RESEARCH_ONLY"
    assert receipt.research_analysis_permitted
    assert not receipt.decision_eligibility_asserted
    assert not receipt.availability_evidence_verified
    assert not receipt.economic_validity_verified
    assert not receipt.source_current_checked
    assert not receipt.replay_authenticity_asserted
    frozen = json.loads(receipt.frozen_input_json)
    assert frozen["request"]["knowledge_cutoff"] is None
    assert frozen["source"]["publication_recorded_at"] == T.isoformat()
    assert receipt.source_evidence_fingerprint == state["evidence"].evidence_fingerprint
    assert run() == receipt
    assert state["calls"] == 2


@pytest.mark.parametrize("days", [-100, 0, 100])
def test_point_in_time_decision_never_promotes_research_or_record_clocks(setup, days):
    _, run = setup
    at = T + timedelta(days=days)
    receipt = run(admission.AdmissionRequest(admission.POINT_IN_TIME, at, at))
    assert receipt.status == "REJECTED"
    assert "RESEARCH_ONLY_PURPOSE_NOT_DECISION_INPUT" in receipt.reason_codes
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in receipt.reason_codes
    assert "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN" in receipt.reason_codes
    assert not receipt.decision_eligibility_asserted
    assert not receipt.research_analysis_permitted


@pytest.mark.parametrize("cutoff,economic", [(None, T), (T, None), (None, None)])
def test_both_point_in_time_axes_required(cutoff, economic):
    with pytest.raises(ValueError, match="BOTH_POINT_IN_TIME_AXES_REQUIRED"):
        admission.AdmissionRequest(admission.POINT_IN_TIME, cutoff, economic)


@pytest.mark.parametrize("cutoff,economic", [(T, None), (None, T), (T, T)])
def test_archival_research_cannot_hide_asof_filters(cutoff, economic):
    with pytest.raises(ValueError, match="ARCHIVAL_RESEARCH_IS_NOT_AN_ASOF_REQUEST"):
        admission.AdmissionRequest(admission.ARCHIVED_RESEARCH, cutoff, economic)


@pytest.mark.parametrize("use_case", ["", "TRADING", "AUTO", "research"])
def test_use_case_must_be_explicit_supported_profile(use_case):
    with pytest.raises(ValueError):
        admission.AdmissionRequest(use_case)


def test_naive_and_non_datetime_clocks_rejected():
    for value in (T.replace(tzinfo=None), True, "2026-01-01"):
        with pytest.raises(ValueError, match="AWARE_ADMISSION_REQUEST_TIME_REQUIRED"):
            admission.AdmissionRequest(admission.POINT_IN_TIME, value, T)


def test_timezones_normalize_and_no_order_is_imposed_between_distinct_axes(setup):
    _, run = setup
    other = T.astimezone(timezone(timedelta(hours=5, minutes=30)))
    first = run(admission.AdmissionRequest(admission.POINT_IN_TIME, T, T + timedelta(days=1)))
    second = run(
        admission.AdmissionRequest(
            admission.POINT_IN_TIME, other, (T + timedelta(days=1)).astimezone(other.tzinfo)
        )
    )
    assert first == second


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "blocked", "research_publication_verified": False, "bundle": None},
        {"reader_version": "research-quote-publication-consumer@2"},
        {"purpose": "DECISION_READY"},
        {"availability_time_known": True},
        {"decision_eligibility_asserted": True},
        {"historical_validity_asserted": True},
        {"source_current_checked": True},
        {"successful_attempt_job_ids": ()},
        {"evidence_fingerprint": None},
    ],
)
def test_source_contract_changes_never_grant_permission(setup, changes):
    state, run = setup
    state["evidence"] = replace(state["evidence"], **changes)
    result = run()
    assert result.status == "REJECTED"
    assert not result.research_analysis_permitted
    assert not result.decision_eligibility_asserted


def test_replay_has_no_database_or_current_source_dependency(setup, monkeypatch):
    _, run = setup
    receipt = run()
    raw = admission.encode_admission_receipt(receipt)

    def fail(*args, **kwargs):
        raise AssertionError("Replay must not query current sources")

    monkeypatch.setattr(admission, "read_research_publication", fail)
    assert (
        admission.replay_admission_receipt(raw, expected_receipt_id=receipt.receipt_id) == receipt
    )


def test_rejected_assessment_replays_identically(setup):
    _, run = setup
    receipt = run(admission.AdmissionRequest(admission.POINT_IN_TIME, T, T))
    assert (
        admission.replay_admission_receipt(
            admission.encode_admission_receipt(receipt), expected_receipt_id=receipt.receipt_id
        )
        == receipt
    )


@pytest.mark.parametrize(
    "change",
    [
        {"status": "ACCEPTED_DECISION"},
        {"decision_eligibility_asserted": True},
        {"decision_eligibility_asserted": 0},
        {"replay_authenticity_asserted": True},
        {"availability_evidence_verified": True},
        {"research_analysis_permitted": 1},
        {"policy_version": "next@2"},
        {"definition_fingerprint": "f" * 64},
    ],
)
def test_tampering_even_with_new_outer_hash_cannot_override_policy(setup, change):
    _, run = setup
    receipt = run(admission.AdmissionRequest(admission.POINT_IN_TIME, T, T))
    value = json.loads(admission.encode_admission_receipt(receipt))
    value.update(change)
    raw = codec.canonical(value).encode()
    with pytest.raises(ValueError):
        admission.replay_admission_receipt(raw, expected_receipt_id=codec.digest(raw))


@pytest.mark.parametrize("kind", ["duplicate", "nonfinite", "whitespace"])
def test_strict_receipt_bytes(setup, kind):
    _, run = setup
    raw = admission.encode_admission_receipt(run())
    if kind == "duplicate":
        raw = raw.replace(b'"status":', b'"status":"bad","status":', 1)
    elif kind == "nonfinite":
        raw = raw.replace(
            b'"decision_eligibility_asserted":false', b'"decision_eligibility_asserted":NaN', 1
        )
    else:
        raw += b" "
    with pytest.raises(ValueError):
        admission.replay_admission_receipt(raw, expected_receipt_id=codec.digest(raw))


def test_input_and_receipt_limits(setup, monkeypatch):
    _, run = setup
    receipt = run()
    raw = admission.encode_admission_receipt(receipt)
    monkeypatch.setattr(admission, "MAX_RECEIPT_BYTES", 1)
    with pytest.raises(ValueError):
        admission.replay_admission_receipt(raw, expected_receipt_id=receipt.receipt_id)
    monkeypatch.setattr(admission, "MAX_RECEIPT_BYTES", 16_777_216)
    monkeypatch.setattr(admission, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="ADMISSION_INPUT_BYTE_LIMIT"):
        run()


def test_future_registry_change_makes_new_receipt_but_old_replay_is_stable(setup):
    state, run = setup
    first = run()
    raw = admission.encode_admission_receipt(first)
    state["evidence"] = replace(state["evidence"], evidence_fingerprint="f" * 64)
    second = run()
    assert first.receipt_id != second.receipt_id
    assert admission.replay_admission_receipt(raw, expected_receipt_id=first.receipt_id) == first


def test_reader_execution_failure_propagates(setup, monkeypatch):
    _, run = setup

    def fail(*args, **kwargs):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(admission, "read_research_publication", fail)
    with pytest.raises(RuntimeError):
        run()


def arguments(tmp_path):
    return [
        "--publication-db",
        str(tmp_path / "registry.duckdb"),
        "--publication-id",
        evidence().publication_id,
        "--use-case",
        admission.ARCHIVED_RESEARCH,
    ]


def test_cli_default_plan_no_execution_imports_or_creation(tmp_path, monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.publication_admission"}:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(arguments(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PLANNED"
    assert list(tmp_path.iterdir()) == []


def test_cli_assess_readonly_registry_connection_and_summary(tmp_path, monkeypatch, capsys):
    path = tmp_path / "registry.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE marker (id INTEGER)")
    connection.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    def read(conn, **kwargs):
        assert conn.execute("SELECT count(*) FROM marker").fetchone() == (0,)
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("INSERT INTO marker VALUES (1)")
        return evidence()

    monkeypatch.setattr(admission, "read_research_publication", read)
    assert cli.main(arguments(tmp_path) + ["--assess"]) == 0
    output = capsys.readouterr().out
    assert "candidate_json" not in output
    assert not json.loads(output)["decision_eligibility_asserted"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_cli_no_unknown_override_or_write_mode(tmp_path):
    for flag in ("--allow-unknown", "--execute", "--initialize", "--allow-trading"):
        with pytest.raises(SystemExit):
            cli.main(arguments(tmp_path) + [flag])


def test_request_axes_are_bound_in_receipt_identity(setup):
    _, run = setup
    first = run(admission.AdmissionRequest(admission.POINT_IN_TIME, T, T))
    second = run(
        admission.AdmissionRequest(admission.POINT_IN_TIME, T + timedelta(microseconds=1), T)
    )
    assert first.receipt_id != second.receipt_id
    assert first.reason_codes == second.reason_codes
    assert not second.decision_eligibility_asserted


def test_replay_checksum_and_source_snapshot_mutation_cannot_be_ignored(setup):
    _, run = setup
    receipt = run()
    raw = admission.encode_admission_receipt(receipt)
    with pytest.raises(ValueError, match="CHECKSUM"):
        admission.replay_admission_receipt(raw + b"x", expected_receipt_id=receipt.receipt_id)
    altered = replace(receipt, frozen_input_json="{}")
    with pytest.raises(ValueError):
        admission.encode_admission_receipt(altered)


def test_cli_decision_assessment_rejects_with_unknown_evidence(tmp_path, monkeypatch, capsys):
    path = tmp_path / "registry.duckdb"
    connection = duckdb.connect(str(path))
    connection.close()
    monkeypatch.setattr(admission, "read_research_publication", lambda *a, **kw: evidence())
    args = arguments(tmp_path)
    args[-1] = admission.POINT_IN_TIME
    args += ["--knowledge-cutoff", T.isoformat(), "--economic-at", T.isoformat(), "--assess"]
    assert cli.main(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "REJECTED"
    assert "AVAILABILITY_EVIDENCE_UNKNOWN" in report["reason_codes"]
    assert not report["decision_eligibility_asserted"]


def test_cli_errors_are_redacted_and_connections_closed(tmp_path, monkeypatch, capsys):
    path = tmp_path / "registry.duckdb"
    connection = duckdb.connect(str(path))
    connection.close()

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET_REGISTRY_DETAILS")

    monkeypatch.setattr(admission, "read_research_publication", fail)
    assert cli.main(arguments(tmp_path) + ["--assess"]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    assert json.loads(output)["reason_code"] == "PUBLICATION_ADMISSION_FAILED"
    connection = duckdb.connect(str(path))
    connection.close()
