"""Pure assertion/byte-integrity tests; no identity authenticity claim."""

import hashlib
from dataclasses import asdict, replace

import pytest

from nse_quant.data_platform import underlying_assertion as kernel

PAYLOAD = b"synthetic evidence only: TEST-ASSET-1"


def request(**changes):
    fields = dict(
        namespace="TEST_NAMESPACE",
        external_id="TEST-ASSET-1",
        asset_kind="INDEX",
        asserted_issuer="TEST_ISSUER",
        assertion="ASSERTED",
        bronze_capture_event_id="a" * 64,
        bronze_envelope_hash="b" * 64,
        evidence_payload_hash=hashlib.sha256(PAYLOAD).hexdigest(),
        evidence_byte_start=0,
        evidence_byte_end=len(PAYLOAD),
        evidence_fragment_sha256=hashlib.sha256(PAYLOAD).hexdigest(),
        rationale_code="TEST_ONLY",
    )
    fields.update(changes)
    return kernel.UnderlyingAssertionRequest(**fields)


def test_assertion_is_not_canonical_identity_or_verification():
    value = kernel.make_underlying_assertion(request())
    assert value.canonical_underlying_id is None
    assert not value.identity_verified
    assert not value.issuer_authenticated
    assert not value.historical_validity_asserted
    assert not value.availability_evidence_verified
    assert not value.decision_eligibility_asserted
    kernel.check_supporting_bytes(request(), PAYLOAD)


@pytest.mark.parametrize("kind", ["ASSERTED", "DISPUTED", "WITHDRAWN"])
def test_all_assertion_states_have_exact_offline_roundtrips(kind):
    value = kernel.make_underlying_assertion(request(assertion=kind))
    raw = kernel.encode_underlying_assertion(value)
    assert (
        kernel.decode_underlying_assertion(raw, expected_assertion_id=value.assertion_id) == value
    )


def test_disputes_and_issuer_changes_share_scope_not_assertion_identity():
    first = kernel.make_underlying_assertion(request())
    for changes in (
        {"assertion": "DISPUTED"},
        {"assertion": "WITHDRAWN"},
        {"asserted_issuer": "OTHER_ISSUER"},
        {"rationale_code": "CHANGED"},
    ):
        changed = kernel.make_underlying_assertion(request(**changes))
        assert changed.subject_scope_id == first.subject_scope_id
        assert changed.assertion_id != first.assertion_id


@pytest.mark.parametrize(
    "changes",
    [
        {"namespace": "other"},
        {"external_id": "TEST-ASSET-2"},
        {"asset_kind": "EQUITY"},
        {"external_id": "test-asset-1"},
    ],
)
def test_exact_scope_no_alias_or_case_inference(changes):
    assert kernel.make_underlying_assertion(request(**changes)).subject_scope_id != (
        kernel.make_underlying_assertion(request()).subject_scope_id
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"namespace": ""},
        {"namespace": " NIFTY"},
        {"external_id": "A" * 257},
        {"asset_kind": "OPTION"},
        {"assertion": "VERIFIED"},
        {"rationale_code": "free text"},
        {"evidence_byte_start": True},
        {"evidence_byte_start": -1},
        {"evidence_byte_end": 0},
        {"evidence_byte_end": 1048577},
        {"bronze_envelope_hash": "BAD"},
        {"evidence_fragment_sha256": False},
    ],
)
def test_bad_requests_fail_before_recording(changes):
    with pytest.raises(ValueError):
        request(**changes)


def test_exact_fragment_not_whole_file_substitute():
    start, end = 10, 18
    value = request(
        evidence_byte_start=start,
        evidence_byte_end=end,
        evidence_fragment_sha256=hashlib.sha256(PAYLOAD[start:end]).hexdigest(),
    )
    kernel.check_supporting_bytes(value, PAYLOAD)
    with pytest.raises(ValueError, match="FRAGMENT_HASH"):
        kernel.check_supporting_bytes(replace(value, evidence_fragment_sha256="f" * 64), PAYLOAD)
    with pytest.raises(ValueError, match="PAYLOAD_HASH"):
        kernel.check_supporting_bytes(value, PAYLOAD + b"x")
    with pytest.raises(ValueError, match="OUTSIDE"):
        kernel.check_supporting_bytes(request(evidence_byte_end=len(PAYLOAD) + 1), PAYLOAD)


@pytest.mark.parametrize(
    "changes",
    [
        {"identity_verified": True},
        {"issuer_authenticated": True},
        {"canonical_underlying_id": "invented"},
        {"historical_validity_asserted": 0},
        {"decision_eligibility_asserted": True},
    ],
)
def test_self_hash_or_type_coercion_cannot_upgrade_claim(changes):
    value = kernel.make_underlying_assertion(request())
    altered = asdict(value)
    altered.update(changes)
    with pytest.raises(ValueError):
        kernel.decode_underlying_assertion(
            kernel.canonical(altered).encode(),
            expected_assertion_id=value.assertion_id,
        )


@pytest.mark.parametrize("kind", ["duplicate", "nonfinite", "whitespace"])
def test_strict_json(kind):
    value = kernel.make_underlying_assertion(request())
    raw = kernel.encode_underlying_assertion(value)
    if kind == "duplicate":
        raw = raw.replace(b'"version":', b'"version":"bad","version":', 1)
    elif kind == "nonfinite":
        raw = raw.replace(b'"identity_verified":false', b'"identity_verified":NaN', 1)
    else:
        raw += b" "
    with pytest.raises(ValueError):
        kernel.decode_underlying_assertion(raw, expected_assertion_id=value.assertion_id)


def test_bounds(monkeypatch):
    value = kernel.make_underlying_assertion(request())
    raw = kernel.encode_underlying_assertion(value)
    monkeypatch.setattr(kernel, "MAX_ASSERTION_BYTES", 1)
    with pytest.raises(ValueError):
        kernel.decode_underlying_assertion(raw, expected_assertion_id=value.assertion_id)
    monkeypatch.setattr(kernel, "MAX_ARTIFACT_BYTES", 1)
    with pytest.raises(ValueError):
        kernel.check_supporting_bytes(request(), PAYLOAD)


def test_default_cli_no_io_no_execution_imports(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.underlying_assertion_cli import main

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"duckdb", "nse_quant.data_platform.underlying_assertion_store"}:
            raise AssertionError("Plan imported execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "bronze.duckdb"),
                "--identity-db",
                str(tmp_path / "identity.duckdb"),
                "--request-file",
                str(tmp_path / "request.json"),
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
