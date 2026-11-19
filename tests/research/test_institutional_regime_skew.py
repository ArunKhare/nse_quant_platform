"""Tests for the institutional regime skew component."""

from __future__ import annotations

import pytest

from nse_quant.research.institutional_regime_skew import (
    InstitutionalRegimeSkewSettings,
    compute_skew,
)


def test_missing_iv_inputs():
    settings = InstitutionalRegimeSkewSettings()
    result = compute_skew(put_iv=None, call_iv=0.2, settings=settings)
    assert result["available"] is False
    assert result["reason"] == "missing_iv_inputs"


def test_invalid_iv_inputs():
    settings = InstitutionalRegimeSkewSettings()
    result = compute_skew(put_iv=-0.1, call_iv=0.2, settings=settings)
    assert result["available"] is False
    assert result["reason"] == "invalid_iv_inputs"


def test_high_put_skew():
    settings = InstitutionalRegimeSkewSettings(skew_threshold=0.03)
    result = compute_skew(put_iv=0.25, call_iv=0.20, settings=settings)
    assert result["available"] is True
    assert result["state"] == "HIGH_PUT_SKEW"
    assert result["skew"] == pytest.approx(0.05)


def test_high_call_skew():
    settings = InstitutionalRegimeSkewSettings(skew_threshold=0.03)
    result = compute_skew(put_iv=0.20, call_iv=0.25, settings=settings)
    assert result["available"] is True
    assert result["state"] == "HIGH_CALL_SKEW"
    assert result["skew"] == pytest.approx(-0.05)


def test_normal_skew():
    settings = InstitutionalRegimeSkewSettings(skew_threshold=0.03)
    result = compute_skew(put_iv=0.21, call_iv=0.20, settings=settings)
    assert result["available"] is True
    assert result["state"] == "NORMAL_SKEW"
    assert result["skew"] == pytest.approx(0.01)
