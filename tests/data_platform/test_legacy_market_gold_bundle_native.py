"""Actual accepted producer fixtures; no successful source DTO replacements."""

import json
from dataclasses import replace

import duckdb
import pytest
from test_legacy_market_gold_native import build
from test_legacy_market_gold_native import native as native
from test_legacy_market_gold_native import pipeline as pipeline
from test_legacy_market_partition_silver_native import bronze_target as bronze_target
from test_legacy_market_partition_silver_native import legacy as legacy

from nse_quant.data_platform import legacy_market_gold_bundle as bundle
from nse_quant.data_platform import legacy_market_gold_store as store


def assemble(native, result, request=None):
    request = request or bundle.LegacyGoldBundleRequest(
        result["build_id"], result["recording_fingerprint"]
    )
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as gold,
    ):
        return bundle.assemble_legacy_gold_bundle(bronze, silver, gold, request=request)


def replay(raw):
    return bundle.replay_legacy_gold_bundle(raw, expected_bundle_id=bundle.gold.sha(raw))


def test_actual_full_native_producer_reader_and_offline_recomputation(native):
    result = build(native)
    raw = assemble(native, result)
    assert replay(raw) == raw
    doc = json.loads(raw)
    assert len(doc["inputs"]) == len(doc["outputs"]) == 1001
    assert doc["request"]["recording_fingerprint"] == result["recording_fingerprint"]
    assert doc["purpose"] == "RESEARCH_ONLY"
    assert doc["publication_asserted"] is False
    assert doc["decision_eligibility_asserted"] is False
    with (
        duckdb.connect(str(native[0][1]), read_only=True) as bronze,
        duckdb.connect(str(native[0][2]), read_only=True) as silver,
        duckdb.connect(str(native[1]), read_only=True) as gold,
    ):
        assert (
            bundle.revalidate_legacy_gold_bundle(
                bronze, silver, gold, raw=raw, expected_bundle_id=bundle.gold.sha(raw)
            )
            == raw
        )


@pytest.mark.parametrize(
    "case",
    [
        "drop-input",
        "drop-output",
        "reverse-input",
        "reverse-output",
        "duplicate",
        "definition",
        "runtime",
        "publication",
        "decision",
        "identity",
        "extra",
        "fingerprint",
    ],
    ids=[
        "drop-in",
        "drop-out",
        "reverse-in",
        "reverse-out",
        "duplicate",
        "definition",
        "runtime",
        "publication",
        "decision",
        "identity",
        "extra",
        "recording-pin",
    ],
)
def test_offline_corruption_even_with_rehashed_outer_bytes(native, case):
    raw = assemble(native, build(native))
    doc = json.loads(raw)
    if case == "drop-input":
        doc["inputs"].pop()
    elif case == "drop-output":
        doc["outputs"].pop()
    elif case == "reverse-input":
        doc["inputs"].reverse()
    elif case == "reverse-output":
        doc["outputs"].reverse()
    elif case == "duplicate":
        doc["outputs"][-1] = doc["outputs"][0]
    elif case == "definition":
        doc["gold_definition"] = "00"
    elif case == "runtime":
        doc["runtime"] = "00"
    elif case == "publication":
        doc["publication_asserted"] = True
    elif case == "decision":
        doc["decision_eligibility_asserted"] = True
    elif case == "identity":
        doc["canonical_contract_id"] = "invented"
    elif case == "extra":
        doc["extra"] = True
    else:
        doc["request"]["recording_fingerprint"] = "bad"
    with pytest.raises(ValueError):
        replay(bundle.gold.canonical(doc))


def test_recording_fingerprint_is_not_offline_authenticated(native):
    result = build(native)
    raw = assemble(native, result)
    doc = json.loads(raw)
    doc["request"]["recording_fingerprint"] = "0" * 64
    changed = bundle.gold.canonical(doc)
    assert replay(changed) == changed
    request = bundle.LegacyGoldBundleRequest(**doc["request"])
    with pytest.raises(ValueError):
        assemble(native, result, request)


@pytest.mark.parametrize(
    "layer", ["bronze", "silver", "gold"], ids=["bronze-audit", "silver-audit", "gold-final-audit"]
)
def test_original_native_audit_failure_is_not_a_bundle(native, layer):
    result = build(native)
    path = {"bronze": native[0][1], "silver": native[0][2], "gold": native[1]}[layer]
    with duckdb.connect(str(path)) as conn:
        table = store.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    with pytest.raises(ValueError):
        assemble(native, result)


def test_retained_content_not_current_native_or_current_legacy(native):
    result = build(native)
    raw = assemble(native, result)
    with duckdb.connect(str(native[0][0])) as conn:
        table = store.name(conn, "main", "spot_candles")
        conn.execute(f"UPDATE {table} SET close=7")
    assert assemble(native, result) == raw
    with duckdb.connect(str(native[0][1])) as conn:
        table = store.name(conn, "medallion_audit", "job_events")
        conn.execute(f"DELETE FROM {table} WHERE state='SUCCEEDED'")
    assert replay(raw) == raw
    with pytest.raises(ValueError):
        assemble(native, result)


def test_second_actual_observation_failure_propagates(native, monkeypatch):
    result = build(native)
    original = store.revalidate_legacy_price_gold
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SYNTHETIC_SECOND_PASS")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "revalidate_legacy_price_gold", observe)
    with pytest.raises(RuntimeError, match="SECOND_PASS"):
        assemble(native, result)
    assert calls == 2


def test_wrong_reviewed_recording_pin(native):
    result = build(native)
    request = bundle.LegacyGoldBundleRequest(result["build_id"], "0" * 64)
    with pytest.raises(ValueError):
        assemble(native, result, request)


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]"], ids=["empty", "object", "array"])
def test_invalid_offline_content(raw):
    with pytest.raises(ValueError):
        replay(raw)


def test_byte_bound_before_json(monkeypatch):
    monkeypatch.setattr(bundle, "MAX_BYTES", 3)
    with pytest.raises(ValueError, match="BYTE_BOUND"):
        replay(b"xxxx")


def test_component_count_preflight(native):
    doc = json.loads(assemble(native, build(native)))
    doc["inputs"] = ["00"] * 16001
    with pytest.raises(ValueError, match="COMPONENT_BOUND"):
        replay(bundle.gold.canonical(doc))


def test_bad_request_type_before_source_access():
    with pytest.raises(TypeError, match="TYPED"):
        bundle.assemble_legacy_gold_bundle(None, None, None, request=None)


def test_request_pin_validation():
    request = bundle.LegacyGoldBundleRequest("a" * 64, "b" * 64)
    with pytest.raises(ValueError):
        replace(request, recording_fingerprint="bad")
