"""Tests for persisted source-linked positions Silver."""

from __future__ import annotations

from nse_quant.data_platform import legacy_positions_silver_store as silver


def test_positions_silver_scope_id_deterministic():
    a = silver.scope_id("fixture")
    b = silver.scope_id("fixture")
    assert a == b and len(a) == 64


def test_positions_silver_scope_id_differs_by_label():
    assert silver.scope_id("fixture") != silver.scope_id("other")


def test_positions_silver_pins_reader_args_roundtrip():
    pins = silver.PositionsBronzePins(
        source_label="fixture",
        snapshot_id="a" * 64,
        capture_event_id="b" * 64,
        envelope_hash="c" * 64,
        recording_fingerprint="d" * 64,
    )
    args = pins.reader_args()
    assert args["source_label"] == "fixture"
    assert args["snapshot_id"] == "a" * 64
    assert args["capture_event_id"] == "b" * 64
    assert args["envelope_hash"] == "c" * 64
    assert args["expected_recording_fingerprint"] == "d" * 64
