"""Source-reconciled native strategy input coverage; no eligibility or healing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.native_strategy_requirements import (
    DEFINITION_SHA256,
    REQUIREMENTS,
    STAGES,
    STRATEGY,
    VERSION,
)


class Rejected(ValueError):
    """Explicit rejection; never a silent coverage pass."""


@dataclass(frozen=True)
class InputCoverage:
    requirement_id: str
    status: str
    evidence_ref: str | None

    def __post_init__(self) -> None:
        if type(self.requirement_id) is not str or not self.requirement_id:
            raise Rejected("EXACT_REQUIREMENT_ID_REQUIRED")
        if self.status not in ("covered", "missing", "unlinked"):
            raise Rejected("EXACT_COVERAGE_STATUS_REQUIRED")
        if self.status == "covered":
            if type(self.evidence_ref) is not str or not self.evidence_ref:
                raise Rejected("COVERED_INPUT_EVIDENCE_REQUIRED")
        elif self.evidence_ref is not None:
            raise Rejected("UNCOVERED_INPUT_EVIDENCE_FORBIDDEN")


def _requirement_ids() -> frozenset[str]:
    return frozenset(requirement_id for requirement_id, _source, _need in REQUIREMENTS)


def reconcile_native_strategy_input_coverage(
    coverage: dict[str, InputCoverage] | None = None,
) -> dict[str, Any]:
    """Reconcile declared coverage against the reviewed requirement inventory.

    This is observational only: it never grants eligibility, heals a gap,
    backfills evidence, or authorizes execution.
    """
    if coverage is None:
        coverage = {}
    if type(coverage) is not dict:
        raise Rejected("EXACT_COVERAGE_MAPPING_REQUIRED")
    known = _requirement_ids()
    unknown = sorted(set(coverage) - known)
    if unknown:
        raise Rejected("UNKNOWN_REQUIREMENT_ID")
    covered: list[str] = []
    missing: list[str] = []
    unlinked: list[str] = []
    for requirement_id, _source, _need in REQUIREMENTS:
        entry = coverage.get(requirement_id)
        if entry is None:
            missing.append(requirement_id)
            continue
        if type(entry) is not InputCoverage:
            raise Rejected("TYPED_INPUT_COVERAGE_REQUIRED")
        if entry.requirement_id != requirement_id:
            raise Rejected("COVERAGE_ID_MISMATCH")
        if entry.status == "covered":
            covered.append(requirement_id)
        elif entry.status == "missing":
            missing.append(requirement_id)
        else:
            unlinked.append(requirement_id)
    identity = coverage.get("authoritative_identity_and_time")
    if identity is not None and identity.status == "covered":
        raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
    return dict(
        version=VERSION,
        strategy=STRATEGY,
        definition_sha256=DEFINITION_SHA256,
        stages=STAGES,
        covered=covered,
        missing=missing,
        unlinked=unlinked,
        complete=len(missing) == 0 and len(unlinked) == 0,
        decision_eligibility_asserted=False,
    )
