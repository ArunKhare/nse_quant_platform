"""Actual ordered window admission consumer. No acquisition/strategy/risk/execution calls."""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform import native_window_refusal as kernel


def evaluate_window_refusal(publications: Any | None, *, request: kernel.RefusalRequest) -> bytes:
    """Early gates do not probe/import window services. Operational failures propagate."""
    if not kernel.common.admission_may_be_observed(request) or publications is None:
        return kernel.make_window_refusal_entry(request)
    from nse_quant.data_platform import legacy_window_admission as policy
    from nse_quant.data_platform.publication_admission import POINT_IN_TIME, AdmissionRequest

    admission_request = AdmissionRequest(
        POINT_IN_TIME, request.knowledge_cutoff, request.economic_at
    )
    args = dict(
        publication_id=request.publication_id,
        expected_recording_fingerprint=request.expected_publication_evidence_fingerprint,
        request=admission_request,
    )
    first = policy.assess_window_publication_use(publications, **args)
    first_raw = policy.encode_window_admission(first)
    second = policy.assess_window_publication_use(publications, **args)
    second_raw = policy.encode_window_admission(second)
    raw = kernel.make_window_refusal_entry(request, admission_receipts=(first_raw, second_raw))
    kernel.replay_window_refusal_entry(raw, expected_decision_id=kernel.sha(raw))
    return raw
