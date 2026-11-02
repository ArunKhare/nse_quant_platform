"""Pure bounds/pin tests only; not native reader integration."""

import hashlib

import pytest

from nse_quant.data_platform.recorded_statement_signature import check_payload_pin


def test_original_bytes_pin():
    raw = b"synthetic\r\n"
    pin = hashlib.sha256(raw).hexdigest()
    assert check_payload_pin(raw, pin) == pin
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        check_payload_pin(raw.replace(b"\r\n", b"\n"), pin)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(bytearray(b"x"), id="mutable"),
        pytest.param(b"x" * 1048577, id="oversized"),
    ],
)
def test_payload_bounds(raw):
    with pytest.raises(ValueError, match="BYTES_REQUIRED"):
        check_payload_pin(raw, "0" * 64)


@pytest.mark.parametrize("pin", ["A" * 64, "x", None, True])
def test_exact_pin_grammar(pin):
    with pytest.raises(ValueError, match="SHA256_REQUIRED"):
        check_payload_pin(b"x", pin)


def test_maximum_bound():
    raw = b"x" * 1048576
    assert check_payload_pin(raw, hashlib.sha256(raw).hexdigest())
