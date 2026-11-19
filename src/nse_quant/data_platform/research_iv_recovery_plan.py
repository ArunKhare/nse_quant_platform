"""Nonexecuting, store-scoped research-IV recovery reconciliation. No mutation API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

VERSION = "research-iv-stage-recovery-reconciliation@1"
MAX_PLAN_BYTES = 262144


@dataclass(frozen=True)
class RecoveryEntry:
    name_sha256: str
    disposition: str


@dataclass(frozen=True)
class ResearchIvRecoveryPlan:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    stage_build_id: str
    expected_stage_fingerprint: str
    inventory_before_fingerprint: str
    inventory_after_fingerprint: str
    entries: tuple[RecoveryEntry, ...]
    evidence_fingerprint: str
    stage_recording_checked: bool = True
    current_source_checked: bool = False
    orphan_status_determined: bool = False
    destructive_actions_authorized: bool = False
    adoption_authorized: bool = False
    retry_authorized: bool = False
    recovery_execution_authorized: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def classify_recovery_entries(
    entries: tuple[tuple[str, str | None, str, int, str | None, bool], ...],
    *,
    bound_name: str,
    bound_sha256: str,
    bound_size: int,
) -> tuple[RecoveryEntry, ...]:
    """Pure classification, NOT a verification or authorization API.

    Input tuples: name digest, safe name, kind, metadata size, content digest, pin match.
    Even an entry absent from this dedicated store can belong to another store.
    """
    if len(entries) > 256:
        raise ValueError("IV_RECOVERY_ENTRY_LIMIT")
    names = [entry[0] for entry in entries]
    if len(set(names)) != len(names):
        raise ValueError("IV_RECOVERY_DUPLICATE_ENTRY")
    result: list[RecoveryEntry] = []
    for name_pin, name, kind, size, content, matches in entries:
        if name == bound_name:
            exact = (
                kind == "PINNED_BYTES_UNASSESSED"
                and size == bound_size
                and content == bound_sha256
                and matches is True
            )
            disposition = "RECORDED_ARTIFACT_RETAIN" if exact else "BOUND_ARTIFACT_REVIEW"
        elif kind == "PINNED_BYTES_UNASSESSED":
            disposition = "OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN"
        else:
            disposition = "UNRESOLVED_ENTRY_RETAIN_FOR_REVIEW"
        result.append(RecoveryEntry(name_pin, disposition))
    return tuple(sorted(result, key=lambda item: item.name_sha256))


def plan_research_iv_stage_recovery(
    staging: Any,
    *,
    stage_build_id_pin: str,
    expected_stage_fingerprint: str,
    artifact_root: Path,
) -> ResearchIvRecoveryPlan:
    """Read stage -> inventory -> inventory -> stage, no source work or writes.

    Unexpected errors propagate, including invalid audit/artifact evidence. There is
    no accepted prefix, automatic latest pin, adoption, cleanup, retry or repair.
    Store ownership is local to this reviewed binding, never a global orphan test.
    """
    from nse_quant.data_platform import research_iv_artifact_inventory as inventory
    from nse_quant.data_platform import research_iv_first_stage as store
    from nse_quant.data_platform import research_iv_stage_record as record

    if (
        store.VERSION != "audited-research-iv-first-stage@1"
        or record.VERSION != "research-iv-first-stage-record@1"
        or inventory.VERSION != "research-iv-artifact-recovery-inventory@1"
        or inventory.MAX_ENTRIES != 256
        or inventory.MAX_ARTIFACT_BYTES != 4194304
        or inventory.MAX_PASS_BYTES != 16777216
    ):
        raise ValueError("IV_RECOVERY_UNSUPPORTED_DEPENDENCY_PROFILE")
    if not record.pin(stage_build_id_pin) or not record.pin(expected_stage_fingerprint):
        raise ValueError("IV_RECOVERY_EXACT_REVIEWED_PINS_REQUIRED")
    # The reader checks the complete original audit and actual canonical artifact.
    before = store.read_research_iv_first_stage(
        staging, build_id_pin=stage_build_id_pin, artifact_root=artifact_root
    )
    if (
        type(before) is not store.ResearchIvFirstStage
        or before.evidence_fingerprint != expected_stage_fingerprint
        or before.build_id != stage_build_id_pin
        or before.status != "verified_research_stage_recording"
        or before.archived_stage_recording_verified is not True
        or before.artifact_bytes_checked is not True
        or before.current_source_checked is not False
        or before.publication_asserted is not False
        or before.decision_eligibility_asserted is not False
        or before.canonical_contract_id is not None
    ):
        raise ValueError("IV_RECOVERY_NOT_EXACT_REVIEWED_STAGE")
    binding = record.decode(before.record_json)
    if record.build_id(before.record_json) != stage_build_id_pin:
        raise ValueError("IV_RECOVERY_STAGE_BINDING_ID_MISMATCH")
    first = inventory.inventory_research_iv_artifacts(artifact_root)
    second = inventory.inventory_research_iv_artifacts(artifact_root)
    after = store.read_research_iv_first_stage(
        staging, build_id_pin=stage_build_id_pin, artifact_root=artifact_root
    )
    stable = asdict(before) == asdict(after) and first == second
    stable = stable and first.unchanged_observed and second.unchanged_observed
    entries = classify_recovery_entries(
        tuple(
            (
                e.name_sha256,
                e.artifact_name,
                e.kind,
                e.size_bytes_metadata,
                e.content_sha256,
                e.filename_pin_matches,
            )
            for e in second.second_pass
        ),
        bound_name=binding["artifact_name"],
        bound_sha256=binding["pins"][2],
        bound_size=binding["artifact_bytes"],
    )
    linked = sum(e.disposition == "RECORDED_ARTIFACT_RETAIN" for e in entries) == 1
    clean = linked and all(e.disposition == "RECORDED_ARTIFACT_RETAIN" for e in entries)
    reasons: list[str] = []
    if not stable:
        reasons.append("IV_RECOVERY_EVIDENCE_CHANGED")
    if not linked:
        reasons.append("IV_RECOVERY_BOUND_ARTIFACT_NOT_OBSERVED")
    if not clean:
        reasons.append("IV_RECOVERY_UNRESOLVED_ENTRIES_RETAIN")
    if not reasons:
        reasons.append("IV_RECOVERY_RECONCILED_NOT_EXECUTION_AUTHORIZATION")
    body: dict[str, Any] = dict(
        version=VERSION,
        status="reconciled_retain_only" if stable and clean else "review_required",
        reason_codes=tuple(reasons),
        stage_build_id=stage_build_id_pin,
        expected_stage_fingerprint=expected_stage_fingerprint,
        inventory_before_fingerprint=first.evidence_fingerprint,
        inventory_after_fingerprint=second.evidence_fingerprint,
        entries=entries,
    )
    # Commit all four complete observations to the evidence digest, not just summary IDs.
    evidence = _canonical([VERSION, asdict(before), asdict(first), asdict(second), asdict(after)])
    result = ResearchIvRecoveryPlan(
        **body, evidence_fingerprint=hashlib.sha256(evidence).hexdigest()
    )
    if len(_canonical(asdict(result))) > MAX_PLAN_BYTES:
        raise ValueError("IV_RECOVERY_PLAN_BYTE_LIMIT")
    return result
