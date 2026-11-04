"""Pure request-scope contract checks, not native source attestation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.data_platform import legacy_market_admission_capture as store
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    POINT_IN_TIME,
    AdmissionRequest,
)


def test_scope_excludes_reviewed_recording_pin():
    pins = store.LegacyAdmissionPins("a" * 64, "b" * 64)
    other = replace(pins, recording_fingerprint="c" * 64)
    request = AdmissionRequest(ARCHIVED_RESEARCH)
    assert store.scope_id(pins.publication_id, request) == store.scope_id(
        other.publication_id, request
    )
    assert store._config(pins, request) != store._config(other, request)


def test_scope_separates_request_axes_and_normalizes_instants():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    local = at.astimezone(timezone(timedelta(hours=5, minutes=30)))
    one = AdmissionRequest(POINT_IN_TIME, at, at)
    two = AdmissionRequest(POINT_IN_TIME, local, local)
    assert store.scope_id("a" * 64, one) == store.scope_id("a" * 64, two)
    later = AdmissionRequest(POINT_IN_TIME, at + timedelta(seconds=1), at)
    assert store.scope_id("a" * 64, one) != store.scope_id("a" * 64, later)
    assert store.scope_id("a" * 64, one) != store.scope_id(
        "a" * 64, AdmissionRequest(ARCHIVED_RESEARCH)
    )


@pytest.mark.parametrize(
    "pin", ["", "bad", "a" * 63, "A" * 64], ids=["empty", "short", "length", "uppercase"]
)
def test_exact_pins(pin):
    with pytest.raises(ValueError):
        store.LegacyAdmissionPins("a" * 64, pin)


def test_naive_axes_not_assigned_utc():
    with pytest.raises(ValueError):
        AdmissionRequest(POINT_IN_TIME, datetime(2026, 1, 1), datetime.now(UTC))


def test_request_type_before_source():
    with pytest.raises(TypeError):
        store.checked_request(None)
