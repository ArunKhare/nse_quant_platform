"""Pure bounded invalidation-first graph resolution. No quality filtering."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass

RESOLVER_VERSION = "native-reference-consumer@1"
MAX_ASSESSMENTS = 1001
MAX_LINKS_PER_ASSESSMENT = 1000


def valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


@dataclass(frozen=True)
class AssessmentNode:
    revision_id: str
    input_revision_id: str
    supersedes: tuple[str, ...]


@dataclass(frozen=True)
class SupersessionResolution:
    reason_code: str
    active_revision_ids: tuple[str, ...] = ()


def resolve_supersession(
    nodes: tuple[AssessmentNode, ...],
    pinned_revision_id: str,
) -> SupersessionResolution:
    """Never discard quarantine/failed/unsupported rows before resolving edges."""
    if not valid_hash(pinned_revision_id):
        return SupersessionResolution("INVALID_ASSESSMENT_PIN")
    if not nodes:
        return SupersessionResolution("ASSESSMENT_NOT_FOUND")
    if len(nodes) > MAX_ASSESSMENTS:
        return SupersessionResolution("ASSESSMENT_HISTORY_LIMIT")
    mapping: dict[str, AssessmentNode] = {}
    group = nodes[0].input_revision_id
    for node in nodes:
        if not valid_hash(node.revision_id) or not valid_hash(node.input_revision_id):
            return SupersessionResolution("INVALID_ASSESSMENT_IDENTITY")
        if node.revision_id in mapping:
            return SupersessionResolution("DUPLICATE_ASSESSMENT_IDENTITY")
        if node.input_revision_id != group:
            return SupersessionResolution("MIXED_INPUT_REVISIONS")
        if (
            not isinstance(node.supersedes, tuple)
            or len(node.supersedes) > MAX_LINKS_PER_ASSESSMENT
        ):
            return SupersessionResolution("SUPERSESSION_LINK_LIMIT")
        if any(not valid_hash(v) for v in node.supersedes):
            return SupersessionResolution("INVALID_SUPERSESSION_LINK")
        if len(set(node.supersedes)) != len(node.supersedes):
            return SupersessionResolution("DUPLICATE_SUPERSESSION_LINK")
        mapping[node.revision_id] = node
    if pinned_revision_id not in mapping:
        return SupersessionResolution("ASSESSMENT_NOT_FOUND")
    superseded: set[str] = set()
    incoming = {key: 0 for key in mapping}
    for node in nodes:
        for older in node.supersedes:
            if older not in mapping:
                return SupersessionResolution("DANGLING_SUPERSESSION_LINK")
            incoming[older] += 1
            superseded.add(older)
    pending = deque(sorted(key for key, count in incoming.items() if count == 0))
    visited = 0
    while pending:
        key = pending.popleft()
        visited += 1
        for older in mapping[key].supersedes:
            incoming[older] -= 1
            if incoming[older] == 0:
                pending.append(older)
    if visited != len(nodes):
        return SupersessionResolution("SUPERSESSION_CYCLE")
    active = tuple(sorted(set(mapping) - superseded))
    if len(active) != 1:
        return SupersessionResolution("AMBIGUOUS_ACTIVE_ASSESSMENTS", active)
    if pinned_revision_id != active[0]:
        return SupersessionResolution("ASSESSMENT_SUPERSEDED", active)
    return SupersessionResolution("ACTIVE_PINNED_ASSESSMENT", active)
