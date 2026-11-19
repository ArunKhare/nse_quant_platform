"""Tests for candidate reconciliation against the accepted current candidate."""

from __future__ import annotations

from nse_quant.data_platform.candidate_reconciliation import (
    DEFINITION_SHA256,
    VERSION,
    reconcile_candidate,
)


def test_matching_candidate_reconciled():
    result = reconcile_candidate(
        candidate_version=VERSION,
        candidate_fingerprint=DEFINITION_SHA256,
    )
    assert result["reconciled"] is True
    assert result["reason"] == "CANDIDATE_RECONCILED"
    assert result["version_match"] is True
    assert result["fingerprint_match"] is True


def test_version_mismatch_refused():
    result = reconcile_candidate(
        candidate_version="other-version",
        candidate_fingerprint=DEFINITION_SHA256,
    )
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_DRIFT_OR_MISMATCH"
    assert result["version_match"] is False
    assert result["fingerprint_match"] is True


def test_fingerprint_mismatch_refused():
    result = reconcile_candidate(
        candidate_version=VERSION,
        candidate_fingerprint="00" * 64,
    )
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_DRIFT_OR_MISMATCH"
    assert result["version_match"] is True
    assert result["fingerprint_match"] is False


def test_both_mismatch_refused():
    result = reconcile_candidate(
        candidate_version="other-version",
        candidate_fingerprint="00" * 64,
    )
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_DRIFT_OR_MISMATCH"
    assert result["version_match"] is False
    assert result["fingerprint_match"] is False


def test_missing_version_refused():
    result = reconcile_candidate(
        candidate_version="",
        candidate_fingerprint=DEFINITION_SHA256,
    )
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_VERSION_REQUIRED"


def test_missing_fingerprint_refused():
    result = reconcile_candidate(
        candidate_version=VERSION,
        candidate_fingerprint="",
    )
    assert result["reconciled"] is False
    assert result["reason"] == "CANDIDATE_FINGERPRINT_REQUIRED"
