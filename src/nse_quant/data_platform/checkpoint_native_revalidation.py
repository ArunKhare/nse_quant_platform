"""Exact retained checkpoint replay plus fresh native policy/receipt observations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.checkpoint_observation import (
    check_reviewed_pins,
    hash_pin,
    observation_digest,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.native_policy_window import NativePolicyWindow
    from nse_quant.data_platform.policy_checkpoint_store import CheckpointView
    from nse_quant.data_platform.signed_policy_window import SignedPolicyInput, SignedPolicyWindow
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "checkpoint-pinned-native-policy-revalidation@1"


@dataclass(frozen=True)
class CheckpointNativeRevalidation:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    expected_checkpoint_id: str
    expected_history_fingerprint: str
    checkpoint_before: CheckpointView | None = None
    checkpoint_after: CheckpointView | None = None
    recording_replay: SignedPolicyWindow | None = None
    native_before: NativePolicyWindow | None = None
    native_after: NativePolicyWindow | None = None
    exact_checkpoint_record_reproduced: bool = False
    retained_head_and_native_scope_bound: bool = False
    evidence_fingerprint: str | None = None
    policy_currentness_verified: bool = False
    policy_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    canonical_underlying_id: None = None
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def revalidate_checkpoint_native_policy(
    checkpoint: Any,
    registry: Any,
    bronze: Any,
    proof_bronze: Any,
    *,
    policy_id: str,
    expected_checkpoint_id: str,
    expected_history_fingerprint: str,
    recording_query: ScopeQuery,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    record_id: str,
    original_plan: bytes,
    expected_plan_sha256: str,
    payload: bytes,
    proof_support: BronzeSupportPin,
    proof_plan: bytes,
    expected_proof_plan_sha256: str,
    expected_public_key_sha256: str,
    snapshots: tuple[SignedPolicyInput, ...],
    governance_public_key: bytes,
    expected_governance_key_sha256: str,
) -> CheckpointNativeRevalidation:
    """No caller checkpoint/native DTO accepted. No writes, opens or auto-latest selection.

    Original recording query is explicit because stored window fingerprints include
    per-query policy results. The assertion's evaluation query remains independently
    derived by the actual native service. Global policy latestness is not asserted.
    """
    from nse_quant.data_platform import native_policy_window as native
    from nse_quant.data_platform import policy_checkpoint_store as store
    from nse_quant.data_platform import signed_policy_window as signed
    from nse_quant.data_platform.policy_checkpoint_record import CheckpointRecord, series_id
    from nse_quant.data_platform.policy_window import PolicyPosition
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery

    if (
        store.VERSION != "audited-policy-checkpoint-store@1"
        or native.VERSION != "native-policy-window-assessment@1"
        or signed.VERSION != "signed-scope-policy-window@1"
    ):
        raise ValueError("UNSUPPORTED_CHECKPOINT_REVALIDATION_DEPENDENCY_VERSION")
    if not hash_pin(expected_checkpoint_id) or not hash_pin(expected_history_fingerprint):
        raise ValueError("EXACT_REVIEWED_CHECKPOINT_REVALIDATION_PINS_REQUIRED")
    if type(recording_query) is not ScopeQuery:
        raise TypeError("EXACT_ORIGINAL_CHECKPOINT_RECORDING_QUERY_REQUIRED")
    recorded_query = ScopeQuery(**asdict(recording_query))
    scope = series_id(policy_id, expected_governance_key_sha256)

    def read() -> store.CheckpointView:
        return store.read_policy_checkpoint(
            checkpoint, policy_id=policy_id, governance_key_sha256=expected_governance_key_sha256
        )

    def failed(
        reasons: tuple[str, ...],
        before: store.CheckpointView | None = None,
        after: store.CheckpointView | None = None,
        replay: signed.SignedPolicyWindow | None = None,
        first: native.NativePolicyWindow | None = None,
        second: native.NativePolicyWindow | None = None,
        reproduced: bool = False,
    ) -> CheckpointNativeRevalidation:
        return CheckpointNativeRevalidation(
            VERSION,
            "review_required",
            reasons,
            expected_checkpoint_id,
            expected_history_fingerprint,
            before,
            after,
            replay,
            first,
            second,
            reproduced,
        )

    try:
        before = read()
    except store.CheckpointReviewRequired:
        return failed(("CHECKPOINT_HISTORY_OR_AUDIT_NOT_COMPLETE_BEFORE",))
    head = before.head
    if (
        type(before) is not store.CheckpointView
        or before.series_id != scope
        or head is None
        or not check_reviewed_pins(
            actual_checkpoint_id=head.checkpoint_id,
            actual_history_fingerprint=before.evidence_fingerprint,
            expected_checkpoint_id=expected_checkpoint_id,
            expected_history_fingerprint=expected_history_fingerprint,
        )
    ):
        return failed(("REVIEWED_CHECKPOINT_IS_NOT_EXACT_RETAINED_HEAD_AND_HISTORY",), before)
    anchor = PolicyPosition(head.anchor_sequence, head.anchor_sha256)
    tip = PolicyPosition(head.tip_sequence, head.tip_sha256)
    replay = signed.inspect_signed_policy_window(
        snapshots,
        governance_public_key=governance_public_key,
        expected_governance_key_sha256=expected_governance_key_sha256,
        query=recorded_query,
        anchor=anchor,
        tip=tip,
    )
    if (
        not replay.window.window_constraints_satisfied
        or not isinstance(replay.evidence_fingerprint, str)
        or not hash_pin(replay.evidence_fingerprint)
    ):
        return failed(("RECORDED_CHECKPOINT_WINDOW_REPLAY_NOT_COMPLETE",), before, replay=replay)
    last = replay.observations[-1]
    reconstructed = CheckpointRecord(
        series_id(last.policy_id, expected_governance_key_sha256),
        head.previous_id,
        anchor.sequence,
        anchor.policy_sha256,
        tip.sequence,
        tip.policy_sha256,
        tuple(sorted(json.loads(snapshots[-1].policy_bytes)["denied_keys"])),
        replay.evidence_fingerprint,
    )
    if reconstructed != head or reconstructed.checkpoint_id != expected_checkpoint_id:
        return failed(("EXACT_CHECKPOINT_RECORD_NOT_REPRODUCED",), before, replay=replay)

    def observe() -> native.NativePolicyWindow:
        return native.inspect_native_policy_window(
            registry,
            bronze,
            proof_bronze,
            assertion_id=assertion_id,
            request=request,
            record_id=record_id,
            original_plan=original_plan,
            expected_plan_sha256=expected_plan_sha256,
            payload=payload,
            proof_support=proof_support,
            proof_plan=proof_plan,
            expected_proof_plan_sha256=expected_proof_plan_sha256,
            expected_public_key_sha256=expected_public_key_sha256,
            snapshots=snapshots,
            governance_public_key=governance_public_key,
            expected_governance_key_sha256=expected_governance_key_sha256,
            anchor=anchor,
            tip=tip,
        )

    def complete(value: native.NativePolicyWindow) -> bool:
        return (
            type(value) is native.NativePolicyWindow
            and value.version == native.VERSION
            and value.status == "observed_policy_window_and_native_scope_satisfied"
            and value.observed_window_and_native_scope_satisfied is True
            and hash_pin(value.evidence_fingerprint)
            and value.native_scope is not None
            and value.canonical_underlying_id is None
            and all(
                flag is False
                for flag in (
                    value.policy_currentness_verified,
                    value.policy_authority_authenticated,
                    value.issuer_authenticated,
                    value.namespace_authority_verified,
                    value.identity_verified,
                    value.authorized_revocation_asserted,
                    value.decision_eligibility_asserted,
                )
            )
        )

    first = observe()
    second = observe()
    try:
        after = read()
    except store.CheckpointReviewRequired:
        return failed(
            ("CHECKPOINT_HISTORY_OR_AUDIT_NOT_COMPLETE_AFTER",),
            before,
            replay=replay,
            first=first,
            second=second,
            reproduced=True,
        )
    reasons: list[str] = []
    if observation_digest(asdict(before)) != observation_digest(asdict(after)):
        reasons.append("CHECKPOINT_HEAD_OR_FULL_HISTORY_CHANGED")
    if not complete(first) or not complete(second):
        reasons.append("CHECKPOINT_NATIVE_SCOPE_NOT_COMPLETE")
    if observation_digest(asdict(first)) != observation_digest(asdict(second)):
        reasons.append("CHECKPOINT_NATIVE_OBSERVATION_DRIFT")
    if reasons:
        return failed(tuple(reasons), before, after, replay, first, second, True)
    fingerprint = observation_digest(
        [
            VERSION,
            expected_checkpoint_id,
            expected_history_fingerprint,
            asdict(recorded_query),
            asdict(before),
            asdict(after),
            asdict(replay),
            asdict(first),
            asdict(second),
        ]
    )
    return CheckpointNativeRevalidation(
        VERSION,
        "retained_checkpoint_and_current_native_scope_bound",
        ("EXACT_RETAINED_CHECKPOINT_REPLAY_AND_NATIVE_OBSERVATIONS_MATCH",),
        expected_checkpoint_id,
        expected_history_fingerprint,
        before,
        after,
        replay,
        first,
        second,
        True,
        True,
        fingerprint,
    )
