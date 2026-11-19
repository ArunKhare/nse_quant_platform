"""Bounded evidence-history and exact recording lifecycle checks; no identity authority."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any


class AssertionReviewRequired(ValueError):
    """Incomplete or invalid evidence; never a rejected/accepted identity claim."""


def instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AssertionReviewRequired("ASSERTION_AWARE_RECORD_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def canonical(value: object) -> str:
    def clock(item: object) -> str:
        return instant(item)

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=clock)


def history_last(graph: dict[str, tuple[str, ...]]) -> str:
    """All-prior evidence links, NOT permission to override or revoke a claim."""
    if not graph or any(
        len(set(edges)) != len(edges) or node in edges or set(edges) - graph.keys()
        for node, edges in graph.items()
    ):
        raise AssertionReviewRequired("ASSERTION_HISTORY_LINKS_INVALID")
    prior: set[str] = set()
    order = sorted(graph, key=lambda node: len(graph[node]))
    for node in order:
        if set(graph[node]) != prior:
            raise AssertionReviewRequired("ASSERTION_HISTORY_INCOMPLETE_OR_FORKED")
        prior.add(node)
    return order[-1]


def lifecycle(rows: list[tuple[Any, ...]]) -> str:
    """Rows: event_index,state,recorded_at,reason. No latest-success shortcut."""
    if not 1 <= len(rows) <= 3:
        raise AssertionReviewRequired("ASSERTION_LIFECYCLE_INVALID")
    if any(type(row[0]) is not int for row in rows) or (
        [row[0] for row in rows] != list(range(1, len(rows) + 1))
    ):
        raise AssertionReviewRequired("ASSERTION_LIFECYCLE_INDEX_INVALID")
    for row in rows:
        instant(row[2])
        if row[3] is not None and (
            not isinstance(row[3], str) or re.fullmatch(r"[A-Z0-9_]{1,64}", row[3]) is None
        ):
            raise AssertionReviewRequired("ASSERTION_LIFECYCLE_REASON_INVALID")
    states = tuple(row[1] for row in rows)
    if states == ("PLANNED", "RUNNING", "SUCCEEDED"):
        if any(row[3] is not None for row in rows):
            raise AssertionReviewRequired("ASSERTION_SUCCESS_REASON_INVALID")
        return "SUCCEEDED"
    if states in {("PLANNED",), ("PLANNED", "RUNNING")}:
        if any(row[3] is not None for row in rows):
            raise AssertionReviewRequired("ASSERTION_PENDING_REASON_INVALID")
        return "INCOMPLETE"
    if states[-1] in {"FAILED", "CANCELLED"} and states[:-1] in {
        ("PLANNED",),
        ("PLANNED", "RUNNING"),
    }:
        if any(row[3] is not None for row in rows[:-1]):
            raise AssertionReviewRequired("ASSERTION_FAILURE_PREFIX_INVALID")
        return states[-1]
    raise AssertionReviewRequired("ASSERTION_LIFECYCLE_INVALID")
