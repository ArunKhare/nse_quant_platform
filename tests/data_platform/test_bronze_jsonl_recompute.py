"""Independent strict decoder/plan tests, not database provenance or issuer authentication."""

import base64
import json

import pytest

from nse_quant.data_platform import bronze_jsonl_recompute as codec


def item(**changes):
    value = dict(
        envelope_version=1,
        source="test",
        capture_session_id="session",
        source_record_id="one",
        received_at="2026-01-01T05:30:00+05:30",
        payload_base64=base64.b64encode(b"\x00\xffdata").decode(),
        payload_format="bytes",
        origin_kind="historical_import",
    )
    value.update(changes)
    return value


def artifact(*rows):
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def plan_bytes(raw, **changes):
    value = dict(
        kind="bronze_event_import",
        version=1,
        input_hash=codec.sha(raw),
        batch_key="batch",
        events=1,
        sources=["test"],
        capture_sessions=["session"],
        target_db="C:\\archived\\bronze.duckdb",
        actor="test",
        code_revision="0646140",
        initialize=True,
    )
    value.update(changes)
    return codec.canonical(value).encode()


def test_exact_payload_and_normalized_receipt_metadata_no_fabricated_exchange_clock():
    raw = artifact(item())
    result = codec.recompute_jsonl(raw)
    event = result.envelopes[0]
    assert event.payload == b"\x00\xffdata"
    assert event.payload_hash == codec.sha(event.payload)
    envelope = json.loads(event.envelope_json)
    assert envelope["received_at"] == "2026-01-01T00:00:00+00:00"
    assert envelope["exchange_ts"] is None
    assert result.artifact_hash == codec.sha(raw)
    assert event.capture_event_id == codec.sha(codec.canonical(["test", "session", "one"]).encode())
    assert event.envelope_hash == codec.sha(event.envelope_json.encode())


def test_raw_whitespace_changes_artifact_hash_not_recomputed_event_bytes():
    first = artifact(item())
    second = b" \n" + first.replace(b"\n", b"\r\n") + b"\t\n"
    a, b = codec.recompute_jsonl(first), codec.recompute_jsonl(second)
    assert a.envelopes == b.envelopes
    assert a.artifact_hash != b.artifact_hash


@pytest.mark.parametrize(
    "changes",
    [
        {"envelope_version": True},
        {"envelope_version": 2},
        {"origin_kind": "invented"},
        {"source": " test"},
        {"received_at": "2026-01-01T00:00:00"},
        {"exchange_ts": ""},
        {"payload_base64": "!!!"},
        {"payload_base64": 1},
        {"provider_event_id": 1},
        {"instrument_ref": ""},
        {"extra": "unknown"},
    ],
)
def test_strict_schema_and_supported_subset(changes):
    with pytest.raises(codec.JsonlRecomputeRejected):
        codec.recompute_jsonl(artifact(item(**changes)))


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\n \n", id="blank"),
        pytest.param(b"[]\n", id="non-object"),
        pytest.param(b"{\n", id="malformed"),
        pytest.param(b"\xff\n", id="non-utf8"),
    ],
)
def test_no_salvage_for_invalid_artifacts(raw):
    with pytest.raises(codec.JsonlRecomputeRejected):
        codec.recompute_jsonl(raw)


def test_duplicate_keys_and_nonfinite_rejected_before_field_selection():
    raw = artifact(item())
    duplicate = raw.replace(b'"source":', b'"source":"other","source":', 1)
    nonfinite = raw.replace(b'"envelope_version": 1', b'"envelope_version": NaN', 1)
    for invalid in (duplicate, nonfinite):
        with pytest.raises(codec.JsonlRecomputeRejected):
            codec.recompute_jsonl(invalid)


def test_duplicate_receipts_not_deduplicated_or_silently_retried():
    with pytest.raises(codec.JsonlRecomputeRejected, match="DUPLICATE_RECEIPT"):
        codec.recompute_jsonl(artifact(item(), item()))


def test_event_order_preserved_and_distinct_receipts_remain_distinct():
    a, b = item(), item(source_record_id="two")
    first = codec.recompute_jsonl(artifact(a, b))
    reversed_order = codec.recompute_jsonl(artifact(b, a))
    assert first.envelopes == tuple(reversed(reversed_order.envelopes))
    assert first.envelopes[0].capture_event_id != first.envelopes[1].capture_event_id


@pytest.mark.parametrize(
    "constant",
    [
        "MAX_ARTIFACT_BYTES",
        "MAX_LINE_BYTES",
        "MAX_EVENTS",
        "MAX_PAYLOAD_BYTES",
        "MAX_TOTAL_PAYLOAD_BYTES",
    ],
)
def test_each_capacity_limit_fails_closed(monkeypatch, constant):
    raw = artifact(item())
    monkeypatch.setattr(codec, constant, 0)
    with pytest.raises(codec.JsonlRecomputeRejected):
        codec.recompute_jsonl(raw)


def test_plan_exact_identity_and_fields_match_decoded_input():
    raw = artifact(item())
    plan_raw = plan_bytes(raw)
    plan = codec.decode_import_plan(plan_raw, expected_plan_sha256=codec.sha(plan_raw))
    codec.verify_plan_inputs(
        plan,
        codec.recompute_jsonl(raw),
        batch_key="batch",
        actor_id="test",
        code_revision="0646140",
    )
    assert plan.plan_sha256 == codec.sha(plan_raw)
    assert "archived" in plan.plan_json


@pytest.mark.parametrize(
    "changes",
    [
        {"version": True},
        {"initialize": 1},
        {"events": True},
        {"events": 0},
        {"sources": ["test", "test"]},
        {"capture_sessions": []},
        {"input_hash": "bad"},
        {"kind": "different"},
        {"unknown": True},
        {"target_db": ""},
    ],
)
def test_invalid_plan_cannot_define_a_new_import_protocol(changes):
    raw = plan_bytes(artifact(item()), **changes)
    with pytest.raises(codec.JsonlRecomputeRejected):
        codec.decode_import_plan(raw, expected_plan_sha256=codec.sha(raw))


@pytest.mark.parametrize(
    "changes",
    [
        {"input_hash": "f" * 64},
        {"batch_key": "other"},
        {"sources": ["other"]},
        {"capture_sessions": ["other"]},
        {"actor": "other"},
        {"code_revision": "other"},
    ],
)
def test_self_consistent_plan_must_still_match_observed_inputs(changes):
    raw = artifact(item())
    plan_raw = plan_bytes(raw, **changes)
    plan = codec.decode_import_plan(plan_raw, expected_plan_sha256=codec.sha(plan_raw))
    with pytest.raises(codec.JsonlRecomputeRejected, match="BINDING"):
        codec.verify_plan_inputs(
            plan,
            codec.recompute_jsonl(raw),
            batch_key="batch",
            actor_id="test",
            code_revision="0646140",
        )


def test_plan_hash_canonical_and_byte_limits(monkeypatch):
    raw = plan_bytes(artifact(item()))
    with pytest.raises(codec.JsonlRecomputeRejected, match="HASH"):
        codec.decode_import_plan(raw, expected_plan_sha256="f" * 64)
    spaced = raw + b" "
    with pytest.raises(codec.JsonlRecomputeRejected, match="CANONICAL"):
        codec.decode_import_plan(spaced, expected_plan_sha256=codec.sha(spaced))
    monkeypatch.setattr(codec, "MAX_PLAN_BYTES", 1)
    with pytest.raises(codec.JsonlRecomputeRejected):
        codec.decode_import_plan(raw, expected_plan_sha256=codec.sha(raw))


def test_cli_no_io_plan_does_not_import_execution(tmp_path, monkeypatch, capsys):
    import builtins

    from nse_quant.data_platform.bronze_jsonl_inspect_cli import main

    original = builtins.__import__

    def guarded(module, *args, **kwargs):
        if module in {"duckdb", "nse_quant.data_platform.bronze_jsonl_support_reader"}:
            raise AssertionError("Plan imported execution")
        return original(module, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert (
        main(
            [
                "--bronze-db",
                str(tmp_path / "absent.duckdb"),
                "--support-file",
                str(tmp_path / "support.json"),
                "--original-plan-file",
                str(tmp_path / "plan.json"),
                "--plan-sha256",
                "a" * 64,
            ]
        )
        == 0
    )
    assert list(tmp_path.iterdir()) == []
    assert "PLANNED" in capsys.readouterr().out
