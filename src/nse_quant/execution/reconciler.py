"""Order reconciliation interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReconciliationResult:
    matched: int
    local_only: list[str]
    broker_only: list[str]
    mismatched: list[str]

    @property
    def clean(self) -> bool:
        return not (self.local_only or self.broker_only or self.mismatched)


class OrderReconciler:
    def reconcile(
        self, local: list[dict[str, Any]], broker: list[dict[str, Any]]
    ) -> ReconciliationResult:
        a = {x["order_id"] for x in local}
        b = {x["order_id"] for x in broker}
        return ReconciliationResult(len(a & b), sorted(a - b), sorted(b - a), [])
