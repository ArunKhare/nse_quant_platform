"""Native source assessment -> ordered pre-strategy refusal. No legacy/execution imports."""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform import native_refusal_decision as kernel


def evaluate_native_refusal(publications: Any | None, *, request: kernel.RefusalRequest) -> bytes:
    """Caller owns file-backed read-only publication source, without an outer transaction.

    Early safety refusal and explicit missing source do not probe or import acquisition,
    strategy, risk, execution or publication services. Operational source errors propagate.
    Two actual complete admission observations must agree; drift is retained as refusal.
    """
    if not kernel.admission_may_be_observed(request) or publications is None:
        return kernel.make_refusal_entry(request)
    from nse_quant.data_platform import publication_admission as policy

    admission_request = policy.AdmissionRequest(
        policy.POINT_IN_TIME,
        request.knowledge_cutoff,
        request.economic_at,
    )
    first = policy.assess_publication_use(
        publications,
        publication_id=request.publication_id,
        request=admission_request,
    )
    first_raw = policy.encode_admission_receipt(first)
    second = policy.assess_publication_use(
        publications,
        publication_id=request.publication_id,
        request=admission_request,
    )
    second_raw = policy.encode_admission_receipt(second)
    raw = kernel.make_refusal_entry(request, admission_receipts=(first_raw, second_raw))
    kernel.replay_refusal_entry(raw, expected_decision_id=kernel.sha(raw))
    return raw
