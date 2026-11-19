"""Untrusted document syntax/content/span tests, not issuer authentication."""

from dataclasses import replace

import pytest

from nse_quant.data_platform import identity_statement_document as document


def record(**changes):
    value = dict(
        statement_schema=document.VERSION,
        record_id="r1",
        namespace="TEST_NS",
        external_id="ASSET1",
        asset_kind="INDEX",
        asserted_issuer="TEST_ISSUER",
        assertion="ASSERTED",
    )
    value.update(changes)
    return document.canonical(value).encode()


def expected(raw, *, body=None, **changes):
    part = record() if body is None else body
    fields = dict(
        record_id="r1",
        namespace="TEST_NS",
        external_id="ASSET1",
        asset_kind="INDEX",
        asserted_issuer="TEST_ISSUER",
        assertion="ASSERTED",
        byte_start=0,
        byte_end=len(part),
        payload_sha256=document.sha(raw),
        fragment_sha256=document.sha(part),
    )
    fields.update(changes)
    return document.StatementExpectation(**fields)


def test_exact_content_and_body_span_do_not_authenticate_identity():
    body = record()
    raw = body + b"\n"
    value = document.match_statement_content(raw, expected=expected(raw))
    assert value.status == "matched_unverified_statement_content"
    assert value.statement_content_matched
    assert value.record_span_verified
    assert value.same_subject_record_ids == ("r1",)
    assert not value.identity_verified
    assert not value.issuer_authenticated
    assert not value.historical_validity_asserted
    assert not value.availability_evidence_verified
    assert not value.decision_eligibility_asserted


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_offsets_are_original_bytes_excluding_line_endings(ending):
    first = record(record_id="other", external_id="OTHER")
    second = record()
    raw = first + ending + second + ending
    start = len(first) + len(ending)
    value = document.match_statement_content(
        raw,
        expected=expected(
            raw,
            byte_start=start,
            byte_end=start + len(second),
        ),
    )
    assert value.statement_content_matched
    parsed = document.parse_statement_document(raw)
    assert parsed.records[1].byte_start == start
    assert raw[parsed.records[1].byte_start : parsed.records[1].byte_end] == second


def test_final_record_without_newline_is_supported():
    raw = record()
    assert document.match_statement_content(raw, expected=expected(raw)).statement_content_matched


@pytest.mark.parametrize(
    "changes",
    [
        {"assertion": "DISPUTED"},
        {"assertion": "WITHDRAWN"},
        {"asserted_issuer": "OTHER"},
        {},
    ],
)
def test_same_subject_conflicts_not_first_last_or_issuer_wins(changes):
    raw = record() + b"\n" + record(record_id="r2", **changes) + b"\n"
    value = document.match_statement_content(raw, expected=expected(raw))
    assert value.status == "review_required"
    assert value.same_subject_record_ids == ("r1", "r2")
    assert not value.statement_content_matched


@pytest.mark.parametrize(
    "changes",
    [
        {"namespace": "other"},
        {"external_id": "OTHER"},
        {"asset_kind": "EQUITY"},
        {"asserted_issuer": "OTHER"},
        {"assertion": "WITHDRAWN"},
    ],
)
def test_claim_fields_must_equal_record_not_just_hash_and_span(changes):
    raw = record() + b"\n"
    value = document.match_statement_content(raw, expected=expected(raw, **changes))
    assert not value.statement_content_matched
    assert value.status == "review_required"


@pytest.mark.parametrize("change", ["payload", "fragment", "span", "record-id"])
def test_all_exact_pins_required(change):
    raw = record() + b"\n"
    value = expected(raw)
    if change == "payload":
        value = replace(value, payload_sha256="f" * 64)
    elif change == "fragment":
        value = replace(value, fragment_sha256="f" * 64)
    elif change == "span":
        value = replace(value, byte_end=value.byte_end + 1)
    else:
        value = replace(value, record_id="missing")
    assert not document.match_statement_content(raw, expected=value).statement_content_matched


@pytest.mark.parametrize(
    "changes",
    [
        {"statement_schema": "unknown@2"},
        {"published_at": "invented"},
        {"asset_kind": True},
        {"assertion": []},
        {"namespace": " TEST_NS"},
        {"external_id": "x" * 257},
        {"record_id": ""},
        {"assertion": "VERIFIED"},
    ],
)
def test_whole_document_schema_rejected(changes):
    later = {"record_id": "later", **changes}
    raw = record() + b"\n" + record(**later) + b"\n"
    with pytest.raises(document.StatementDocumentRejected):
        document.match_statement_content(raw, expected=expected(raw))


def test_duplicate_ids_even_unrelated_subjects_reject_document():
    raw = record() + b"\n" + record(external_id="OTHER") + b"\n"
    with pytest.raises(document.StatementDocumentRejected, match="DUPLICATE_RECORD"):
        document.parse_statement_document(raw)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\n", id="blank"),
        pytest.param(b"\xff", id="non-utf8"),
        pytest.param(b"{}", id="wrong-schema"),
    ],
)
def test_malformed_payloads_are_not_prefix_salvaged(raw):
    with pytest.raises(document.StatementDocumentRejected):
        document.parse_statement_document(raw)


def test_duplicate_nonfinite_whitespace_and_bare_cr_rejected():
    body = record()
    cases = [
        body.replace(b'"namespace":', b'"namespace":"other","namespace":', 1),
        body.replace(b'"asset_kind":"INDEX"', b'"asset_kind":NaN', 1),
        b" " + body,
        body + b"\r",
        body + b"\n\n",
    ]
    for raw in cases:
        with pytest.raises(document.StatementDocumentRejected):
            document.parse_statement_document(raw)


@pytest.mark.parametrize("constant", ["MAX_PAYLOAD_BYTES", "MAX_RECORD_BYTES", "MAX_RECORDS"])
def test_capacity_never_returns_partial_match(monkeypatch, constant):
    raw = record() + b"\n"
    monkeypatch.setattr(document, constant, 0)
    with pytest.raises(document.StatementDocumentRejected):
        document.parse_statement_document(raw)


def test_bool_offsets_and_invalid_hashes_rejected_before_selection():
    raw = record()
    for changes in ({"byte_start": False}, {"payload_sha256": "bad"}):
        with pytest.raises(ValueError):
            expected(raw, **changes)


def test_no_io_cli_plan_and_execution_import_guard(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.identity_statement_inspect_cli import main

    original = builtins.__import__

    def guarded(module, *args, **kwargs):
        if module in {"duckdb", "nse_quant.data_platform.identity_statement_reader"}:
            raise AssertionError("Plan imported execution")
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--identity-db",
                str(tmp_path / "identity.duckdb"),
                "--bronze-db",
                str(tmp_path / "bronze.duckdb"),
                "--assertion-id",
                "a" * 64,
                "--record-id",
                "r1",
                "--request-file",
                str(tmp_path / "request.json"),
                "--original-plan-file",
                str(tmp_path / "plan.json"),
                "--plan-sha256",
                "b" * 64,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
