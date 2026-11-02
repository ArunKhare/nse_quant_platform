"""Pure reviewed-pin and DTO digest tests, not native checkpoint revalidation."""

import hashlib
from datetime import UTC, datetime

import pytest

from nse_quant.data_platform.checkpoint_observation import (
    check_reviewed_pins,
    observation_digest,
)


def pins(**changes):
    values = dict(
        actual_checkpoint_id="a" * 64,
        actual_history_fingerprint="b" * 64,
        expected_checkpoint_id="a" * 64,
        expected_history_fingerprint="b" * 64,
    )
    values.update(changes)
    return check_reviewed_pins(**values)


def test_both_reviewed_pins_required():
    assert pins()
    assert not pins(actual_checkpoint_id="c" * 64)
    assert not pins(actual_history_fingerprint="c" * 64)


@pytest.mark.parametrize(
    "field",
    [
        "actual_checkpoint_id",
        "actual_history_fingerprint",
        "expected_checkpoint_id",
        "expected_history_fingerprint",
    ],
)
@pytest.mark.parametrize("bad", [None, "bad", "A" * 64, True])
def test_no_malformed_pin_fallback(field, bad):
    with pytest.raises(ValueError):
        pins(**{field: bad})


def test_digest_preserves_mapping_order_independence_and_byte_changes():
    assert observation_digest({"a": 1, "b": b"key"}) == observation_digest({"b": b"key", "a": 1})
    assert observation_digest({"b": b"key"}) != observation_digest({"b": b"other"})


def test_type_tags_cannot_be_spoofed_by_json_mapping():
    raw = b"key"
    forged = {"original_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert observation_digest(raw) != observation_digest(forged)
    assert observation_digest((1, 2)) != observation_digest([1, 2])
    assert observation_digest(True) != observation_digest(1)
    assert observation_digest(1.0) != observation_digest(1)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_rejected(value):
    with pytest.raises(ValueError):
        observation_digest(value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(bytearray(b"x"), id="mutable-bytes"),
        pytest.param(datetime(2026, 1, 1, tzinfo=UTC), id="unprojected-clock"),
        pytest.param({1: "value"}, id="nonstring-key"),
    ],
)
def test_unknown_values_not_stringified(value):
    with pytest.raises(TypeError):
        observation_digest(value)
