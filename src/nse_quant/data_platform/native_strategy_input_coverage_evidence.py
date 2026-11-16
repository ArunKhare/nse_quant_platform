"""Evidence-linked native strategy input coverage; no eligibility or healing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.native_strategy_input_coverage import (
    InputCoverage,
    Rejected,
    reconcile_native_strategy_input_coverage,
)
from nse_quant.data_platform.native_strategy_requirements import (
    REQUIREMENTS,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidencePin:
    requirement_id: str
    revision_id: str
    recording_fingerprint: str
    row_count: int

    def __post_init__(self) -> None:
        if type(self.requirement_id) is not str or not self.requirement_id:
            raise Rejected("EXACT_REQUIREMENT_ID_REQUIRED")
        if not _HEX64.fullmatch(self.revision_id):
            raise Rejected("EXACT_REVISION_PIN_REQUIRED")
        if not _HEX64.fullmatch(self.recording_fingerprint):
            raise Rejected("EXACT_RECORDING_FINGERPRINT_REQUIRED")
        if type(self.row_count) is not int or isinstance(self.row_count, bool) or self.row_count < 1:
            raise Rejected("POSITIVE_ROW_COUNT_REQUIRED")


def derive_native_strategy_input_coverage(
    evidence: dict[str, EvidencePin] | None = None,
) -> dict[str, Any]:
    """Derive coverage from explicit pinned Silver evidence; observational only.

    Never grants eligibility, heals a gap, backfills evidence, or authorizes execution.
    """
    if evidence is None:
        evidence = {}
    if type(evidence) is not dict:
        raise Rejected("EXACT_EVIDENCE_MAPPING_REQUIRED")
    known = frozenset(requirement_id for requirement_id, _s, _n in REQUIREMENTS)
    unknown = sorted(set(evidence) - known)
    if unknown:
        raise Rejected("UNKNOWN_REQUIREMENT_ID")
    coverage: dict[str, InputCoverage] = {}
    evidence_refs: dict[str, str] = {}
    for requirement_id, _source, _need in REQUIREMENTS:
        pin = evidence.get(requirement_id)
        if pin is None:
            coverage[requirement_id] = InputCoverage(requirement_id=requirement_id, status="missing", evidence_ref=None)
            continue
        if type(pin) is not EvidencePin:
            raise Rejected("TYPED_EVIDENCE_PIN_REQUIRED")
        if pin.requirement_id != requirement_id:
            raise Rejected("EVIDENCE_ID_MISMATCH")
        if requirement_id == "authoritative_identity_and_time":
            raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
        ref = (
            f"silver://{requirement_id}"
            f"?revision_id={pin.revision_id}"
            f"&recording_fingerprint={pin.recording_fingerprint}"
            f"&row_count={pin.row_count}"
        )
        coverage[requirement_id] = InputCoverage(requirement_id=requirement_id, status="covered", evidence_ref=ref)
        evidence_refs[requirement_id] = ref
    report = reconcile_native_strategy_input_coverage(coverage)
    report["evidence_refs"] = evidence_refs
    return report
