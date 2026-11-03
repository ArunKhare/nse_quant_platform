"""Read-only current stage/artifact reconciliation of an exact reviewed recovery capture."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_recovery_capture_observation import (
    MAX_PLAN_BYTES,
    RecoveryCaptureComparison,
    compare_recovery_capture_plans,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.research_iv_recovery_capture import ResearchIvRecoveryCapture
    from nse_quant.data_platform.research_iv_recovery_plan import ResearchIvRecoveryPlan

VERSION = "research-iv-recovery-capture-current-reconciliation@1"


@dataclass(frozen=True)
class ResearchIvCurrentRecoveryCapture:
    version: str
    capture_build_id: str
    expected_capture_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    capture_before: ResearchIvRecoveryCapture | None = None
    capture_after: ResearchIvRecoveryCapture | None = None
    fresh_before: ResearchIvRecoveryPlan | None = None
    fresh_after: ResearchIvRecoveryPlan | None = None
    comparison: RecoveryCaptureComparison | None = None
    archived_recording_verified: bool = False
    current_reconciliation_checked: bool = False
    exact_recorded_plan_reproduced: bool = False
    capture_unchanged_observed: bool = False
    plan_evidence_fingerprint: str | None = None
    evidence_fingerprint: str | None = None
    current_source_checked: bool = False
    orphan_status_determined: bool = False
    destructive_actions_authorized: bool = False
    adoption_authorized: bool = False
    retry_authorized: bool = False
    recovery_execution_authorized: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    option_underlying_identity_binding_verified: bool = False
    scenario_terms_authoritative: bool = False
    model_suitability_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def revalidate_research_iv_recovery_capture(
    staging: Any,
    capture: Any,
    *,
    capture_build_id_pin: str,
    expected_capture_fingerprint: str,
    artifact_root: Path,
) -> ResearchIvCurrentRecoveryCapture:
    """Reconstruct frozen inputs only from the actual verified record. No writes.

    Retained review outcomes stop before stage/filesystem/native work. Unexpected
    native/codec/DB/filesystem exceptions propagate; no accepted partial return.
    """
    from nse_quant.data_platform import research_iv_recovery_capture as store
    from nse_quant.data_platform import research_iv_recovery_capture_record as record
    from nse_quant.data_platform import research_iv_recovery_plan as native

    if (
        store.VERSION != "audited-research-iv-recovery-capture@1"
        or record.VERSION != "research-iv-recovery-capture-record@1"
        or native.VERSION != "research-iv-stage-recovery-reconciliation@1"
        or record.SERVICE_VERSION != native.VERSION
        or record.MAX_RECORD_BYTES != 270336
        or native.MAX_PLAN_BYTES != MAX_PLAN_BYTES
    ):
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_UNSUPPORTED_PROFILE")
    if not record.pin(capture_build_id_pin) or not record.pin(expected_capture_fingerprint):
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_EXACT_REVIEWED_PINS_REQUIRED")

    def report(reasons: tuple[str, ...], **facts: Any) -> ResearchIvCurrentRecoveryCapture:
        return ResearchIvCurrentRecoveryCapture(
            VERSION,
            capture_build_id_pin,
            expected_capture_fingerprint,
            "review_required",
            reasons,
            **facts,
        )

    def read_capture() -> store.ResearchIvRecoveryCapture:
        return store.read_research_iv_recovery_capture(capture, build_id_pin=capture_build_id_pin)

    def complete_recording(value: store.ResearchIvRecoveryCapture) -> bool:
        return (
            type(value) is store.ResearchIvRecoveryCapture
            and value.version == store.VERSION
            and value.build_id == capture_build_id_pin
            and value.status == "recorded_recovery_observation_not_execution_authorization"
            and value.original_recording_checked is True
            and value.current_reconciliation_checked is False
            and all(
                getattr(value, key) is False
                for key in (
                    "recovery_execution_authorized",
                    "publication_asserted",
                    "decision_eligibility_asserted",
                )
            )
            and value.event_ts is None
            and value.published_at is None
            and record.pin(value.evidence_fingerprint)
        )

    try:
        before = read_capture()
    except store.IvRecoveryCaptureReviewRequired:
        return report(("RECOVERY_CAPTURE_ORIGINAL_RECORDING_INCOMPLETE_BEFORE",))
    if (
        not complete_recording(before)
        or before.evidence_fingerprint != expected_capture_fingerprint
    ):
        return report(("RECOVERY_CAPTURE_NOT_EXACT_REVIEWED_RECORDING",), capture_before=before)
    body = record.decode(before.record_json)
    if record.sha(before.record_json.encode()) != capture_build_id_pin:
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_BINDING_ID_MISMATCH")
    frozen = body["plan"]
    facts: dict[str, Any] = dict(capture_before=before, archived_recording_verified=True)
    if frozen["status"] != "reconciled_retain_only":
        return report(("RECORDED_RECOVERY_REVIEW_CANNOT_BE_UPGRADED",), **facts)
    # No filesystem work precedes verification of the reviewed original recording.
    if (
        not isinstance(artifact_root, Path)
        or not artifact_root.is_absolute()
        or ".." in artifact_root.parts
        or str(artifact_root) != body["artifact_root"]
    ):
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_EXACT_RECORDED_ROOT_REQUIRED")
    if staging is capture or any(
        a == b or a.samefile(b) for a in store._paths(staging) for b in store._paths(capture)
    ):
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_SEPARATE_DATABASE_REQUIRED")
    for path in (artifact_root, *artifact_root.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_REDIRECTED_ROOT")
    databases = (*store._paths(staging), *store._paths(capture))
    resolved = artifact_root.resolve()
    for path in databases:
        selected = path.resolve()
        if resolved == selected or resolved in selected.parents or selected in resolved.parents:
            raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_DATABASE_ROOT_OVERLAP")
    if any(child.samefile(path) for child in artifact_root.iterdir() for path in databases):
        raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_DATABASE_ARTIFACT_HARDLINK")
    recorded_raw = record.canonical(frozen).encode()

    def observe() -> tuple[native.ResearchIvRecoveryPlan, bytes]:
        value = native.plan_research_iv_stage_recovery(
            staging,
            stage_build_id_pin=frozen["stage_build_id"],
            expected_stage_fingerprint=frozen["expected_stage_fingerprint"],
            artifact_root=artifact_root,
        )
        if type(value) is not native.ResearchIvRecoveryPlan:
            raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_TYPED_NATIVE_PLAN_REQUIRED")
        # Exact @1 codec validates complete result fields, denials, entry/reason bounds.
        encoded = record.encode(str(artifact_root), asdict(value))
        validated = record.decode(encoded)["plan"]
        if (
            validated["stage_build_id"] != frozen["stage_build_id"]
            or validated["expected_stage_fingerprint"] != frozen["expected_stage_fingerprint"]
        ):
            raise ValueError("IV_CURRENT_RECOVERY_CAPTURE_NATIVE_SCOPE_MISMATCH")
        return value, record.canonical(validated).encode()

    first, first_raw = observe()
    second, second_raw = observe()
    comparison = compare_recovery_capture_plans(recorded_raw, first_raw, second_raw)
    reproduced = comparison.all_plan_bytes_match and (
        first.status == second.status == "reconciled_retain_only"
    )
    reasons = list(comparison.reason_codes)
    if first.status != "reconciled_retain_only" or second.status != "reconciled_retain_only":
        reasons.append("CURRENT_RECOVERY_RECONCILIATION_REQUIRES_REVIEW")
    facts.update(
        fresh_before=first,
        fresh_after=second,
        comparison=comparison,
        current_reconciliation_checked=True,
        exact_recorded_plan_reproduced=reproduced,
    )
    try:
        after = read_capture()
    except store.IvRecoveryCaptureReviewRequired:
        reasons.append("RECOVERY_CAPTURE_ORIGINAL_RECORDING_INCOMPLETE_AFTER")
        return report(tuple(reasons), **facts)
    stable = complete_recording(after) and asdict(before) == asdict(after)
    facts.update(capture_after=after, capture_unchanged_observed=stable)
    if not stable:
        reasons.append("RECOVERY_CAPTURE_RECORDING_OR_AUDIT_CHANGED")
    if reasons:
        return report(tuple(reasons), **facts)
    fingerprint = record.sha(
        record.canonical(
            [
                VERSION,
                capture_build_id_pin,
                expected_capture_fingerprint,
                asdict(before),
                asdict(first),
                asdict(second),
                asdict(after),
                asdict(comparison),
            ]
        ).encode()
    )
    return ResearchIvCurrentRecoveryCapture(
        VERSION,
        capture_build_id_pin,
        expected_capture_fingerprint,
        "matched_current_research_iv_recovery_capture",
        ("RETAINED_PLAN_BYTES_REPRODUCED_NOT_RECOVERY_AUTHORIZATION",),
        plan_evidence_fingerprint=frozen["evidence_fingerprint"],
        evidence_fingerprint=fingerprint,
        **facts,
    )
