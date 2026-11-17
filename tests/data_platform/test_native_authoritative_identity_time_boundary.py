"""Tests for the authoritative identity and time boundary."""

from __future__ import annotations

from typing import Any

import pytest

from nse_quant.data_platform.native_authoritative_identity_time_boundary import (
    VERSION,
    authoritative_boundary_context,
    validate_authoritative_identity_time_boundary,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _document() -> dict[str, Any]:
    return {
        "version": VERSION,
        "requirement": "authoritative_identity_and_time",
        "identity": {
            "canonical_underlying": "NIFTY",
            "source": "exchange_master",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "derivative": {
            "binding": "canonical_underlying_to_derivative",
            "revision_id": "c" * 64,
            "recording_fingerprint": "d" * 64,
        },
        "authorized_revocation": {
            "authorized": True,
            "revision_id": "e" * 64,
            "recording_fingerprint": "f" * 64,
        },
        "point_in_time_decision": False,
        "auto_coverable": False,
        "decision_eligibility_asserted": False,
    }


def test_validates_authoritative_boundary() -> None:
    document = _document()
    result = validate_authoritative_identity_time_boundary(document)
    assert result["valid"] is True
    assert result["requirement"] == "authoritative_identity_and_time"
    assert result["decision_eligibility_asserted"] is False
    assert authoritative_boundary_context(document) == result["document_sha256"]


def test_point_in_time_decision_rejected() -> None:
    document = _document()
    document["point_in_time_decision"] = True
    with pytest.raises(Rejected, match="POINT_IN_TIME_DECISION"):
        validate_authoritative_identity_time_boundary(document)


def test_auto_coverable_rejected() -> None:
    document = _document()
    document["auto_coverable"] = True
    with pytest.raises(Rejected, match="AUTHORITATIVE_BOUNDARY_NOT_AUTO_COVERABLE"):
        validate_authoritative_identity_time_boundary(document)


def test_invalid_underlying_rejected() -> None:
    document = _document()
    document["identity"]["canonical_underlying"] = "UNKNOWN"
    with pytest.raises(Rejected, match="AUTHORITATIVE_CANONICAL_UNDERLYING_INVALID"):
        validate_authoritative_identity_time_boundary(document)


def test_unauthorized_revocation_rejected() -> None:
    document = _document()
    document["authorized_revocation"]["authorized"] = False
    with pytest.raises(Rejected, match="AUTHORITATIVE_REVOCATION_NOT_AUTHORIZED"):
        validate_authoritative_identity_time_boundary(document)
