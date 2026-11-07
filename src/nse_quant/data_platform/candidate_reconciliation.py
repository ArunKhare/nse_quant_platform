"""Candidate reconciliation against the accepted current candidate.

Reconciles the accepted current candidate's version/fingerprint against the
requirements inventory (native_strategy_requirements.py), flagging drift or
mismatch without synthesizing identity or granting eligibility. Addresses the
"reconcile uncovered inputs against the accepted current candidate" sub-gap of
gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    REQUIREMENTS,
    VERSION,
)


def reconcile_candidate(
    *,
    candidate_version: str,
    candidate_fingerprint: str,
) -> dict[str, Any]:
    """Reconcile a candidate's version/fingerprint against the requirements inventory."""
    if type(candidate_version) is not str or not candidate_version:
        return dict(
            reconciled=False,
            reason="CANDIDATE_VERSION_REQUIRED",
            version_match=False,
            fingerprint_match=False,
        )
    if type(candidate_fingerprint) is not str or not candidate_fingerprint:
        return dict(
            reconciled=False,
            reason="CANDIDATE_FINGERPRINT_REQUIRED",
            version_match=False,
            fingerprint_match=False,
        )

    version_match = candidate_version == VERSION
    fingerprint_match = candidate_fingerprint == DEFINITION_SHA256
    reconciled = version_match and fingerprint_match
    return dict(
        reconciled=reconciled,
        reason="CANDIDATE_RECONCILED" if reconciled else "CANDIDATE_DRIFT_OR_MISMATCH",
        version_match=version_match,
        fingerprint_match=fingerprint_match,
        expected_version=VERSION,
        expected_fingerprint=DEFINITION_SHA256,
        requirements_count=len(REQUIREMENTS),
    )
