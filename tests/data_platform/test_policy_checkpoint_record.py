"""Pure checkpoint constraints; not native writer/audit verification."""

from dataclasses import replace

import pytest

from nse_quant.data_platform.policy_checkpoint_record import (
    CheckpointRecord,
    series_id,
    validate_extension,
)


def record(**changes):
    values = dict(
        series_id=series_id("TEST", "a" * 64),
        previous_id=None,
        anchor_sequence=1,
        anchor_sha256="1" * 64,
        tip_sequence=2,
        tip_sha256="2" * 64,
        denied_keys=(),
        window_fingerprint="b" * 64,
    )
    values.update(changes)
    return CheckpointRecord(**values)


def extension(previous, **changes):
    values = dict(
        previous_id=previous.checkpoint_id,
        anchor_sequence=previous.tip_sequence,
        anchor_sha256=previous.tip_sha256,
        tip_sequence=previous.tip_sequence + 1,
        tip_sha256="3" * 64,
        denied_keys=previous.denied_keys,
    )
    values.update(changes)
    return record(**values)


def test_genesis_and_continuation():
    first = record()
    validate_extension(None, first)
    validate_extension(first, extension(first))
    assert first.checkpoint_id == record().checkpoint_id


@pytest.mark.parametrize(
    "changes",
    [
        {"previous_id": "e" * 64},
        {"anchor_sha256": "e" * 64},
        {"series_id": series_id("OTHER", "a" * 64)},
        {"tip_sequence": 2},
    ],
    ids=["wrong-head", "wrong-anchor", "wrong-series", "no-advance"],
)
def test_no_stale_or_forked_extension(changes):
    first = record()
    with pytest.raises(ValueError):
        validate_extension(first, extension(first, **changes))


def test_denial_cannot_be_lost_across_windows():
    first = record(denied_keys=("a" * 64,))
    with pytest.raises(ValueError, match="DENIAL_REMOVAL"):
        validate_extension(first, extension(first, denied_keys=()))
    validate_extension(first, extension(first, denied_keys=("a" * 64, "b" * 64)))


@pytest.mark.parametrize(
    "changes",
    [
        {"anchor_sequence": True},
        {"tip_sequence": 2147483648},
        {"anchor_sha256": "bad"},
        {"denied_keys": ("b" * 64, "a" * 64)},
        {"denied_keys": ("a" * 64, "a" * 64)},
        {"denied_keys": []},
        {"previous_id": "bad"},
    ],
    ids=["bool", "bound", "hash", "unsorted", "duplicate", "mutable", "bad-parent"],
)
def test_record_shape(changes):
    with pytest.raises(ValueError):
        record(**changes)


def test_genesis_does_not_accept_missing_predecessor():
    with pytest.raises(ValueError):
        validate_extension(None, record(previous_id="e" * 64))


def test_key_change_is_different_local_series_not_trusted_rotation():
    assert series_id("TEST", "a" * 64) != series_id("TEST", "b" * 64)


def test_changed_window_is_not_exact_retry():
    first = record()
    assert first.checkpoint_id != replace(first, window_fingerprint="c" * 64).checkpoint_id
