"""Explicit assertion-request to current Bronze storage check; no registry authority claim."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nse_quant.data_platform.bronze_support_reader import (
    BronzeSupportEvidence,
    BronzeSupportPin,
    IngestAuditExpectation,
    inspect_bronze_support,
)
from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest


def inspect_underlying_support_storage(
    bronze: Any,
    *,
    request: UnderlyingAssertionRequest,
    expected_audit: IngestAuditExpectation,
) -> BronzeSupportEvidence:
    """Supplied request is NOT verified as a recorded/current assertion by this API.

    Compose with the committed archived consumer separately after local interface
    reconciliation. No reliance on an uninspected newer reader snapshot, no repair.
    """
    if not isinstance(request, UnderlyingAssertionRequest):
        raise TypeError("TYPED_UNDERLYING_SUPPORT_REQUEST_REQUIRED")
    checked = UnderlyingAssertionRequest(**asdict(request))
    support = BronzeSupportPin(
        checked.bronze_capture_event_id,
        checked.bronze_envelope_hash,
        checked.evidence_payload_hash,
        checked.evidence_byte_start,
        checked.evidence_byte_end,
        checked.evidence_fragment_sha256,
    )
    return inspect_bronze_support(bronze, support=support, expected_audit=expected_audit)
