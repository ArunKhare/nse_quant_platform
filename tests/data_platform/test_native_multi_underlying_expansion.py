"""Tests for multi-underlying expansion validation."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_multi_underlying_expansion import (
    validate_multi_underlying_expansion,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document(underlying: str) -> dict[str, Any]:
    return {
        "version": "native-multi-underlying-expansion@1",
        "canonical_underlying": underlying,
        "derivative": {
            "binding": "canonical_underlying_to_derivative",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def test_validates_nifty() -> None:
    result = validate_multi_underlying_expansion(_document("NIFTY"))
    assert result["valid"] is True
    assert result["canonical_underlying"] == "NIFTY"
    assert result["decision_eligibility_asserted"] is False


def test_validates_banknifty() -> None:
    result = validate_multi_underlying_expansion(_document("BANKNIFTY"))
    assert result["valid"] is True
    assert result["canonical_underlying"] == "BANKNIFTY"
    assert result["decision_eligibility_asserted"] is False


def test_rejects_unknown_underlying() -> None:
    with pytest.raises(Rejected, match="MULTI_UNDERLYING_CANONICAL_UNDERLYING_INVALID"):
        validate_multi_underlying_expansion(_document("UNKNOWN"))


def test_rejects_point_in_time_decision() -> None:
    document = _document("NIFTY")
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_multi_underlying_expansion(document)


def test_rejects_invalid_binding() -> None:
    document = _document("NIFTY")
    document["derivative"]["binding"] = "invalid"
    with pytest.raises(Rejected, match="MULTI_UNDERLYING_DERIVATIVE_BINDING_INVALID"):
        validate_multi_underlying_expansion(document)
