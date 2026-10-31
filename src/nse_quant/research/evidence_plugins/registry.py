"""Safe runner for observational evidence plugins."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvidenceResult:
    plugin: str
    available: bool
    complete: bool | None
    payload: dict[str, Any]


class EvidencePluginRunner:
    def __init__(self, plugins: list[EvidencePlugin] | None = None) -> None:
        self.plugins = plugins or []

    def run(self, context: DecisionContext) -> list[EvidenceResult]:
        results: list[EvidenceResult] = []

        for plugin in self.plugins:
            try:
                payload = plugin.build(context)
                results.append(
                    EvidenceResult(
                        plugin=plugin.name,
                        available=bool(payload.get("available", False)),
                        complete=payload.get("complete"),
                        payload=payload,
                    )
                )
            except (AttributeError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                logger.warning(
                    "Evidence plugin %s failed: %s",
                    plugin.name,
                    exc,
                )

                results.append(
                    EvidenceResult(
                        plugin=plugin.name,
                        available=False,
                        complete=False,
                        payload={
                            "available": False,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                )

        return results
