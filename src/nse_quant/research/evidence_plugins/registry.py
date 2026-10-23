"""Safe runner for observational evidence plugins."""

from __future__ import annotations

import logging
from typing import Any

from nse_quant.research.evidence_plugins.base import (
    DecisionContext,
    EvidencePlugin,
)

logger = logging.getLogger(__name__)


class EvidencePluginRunner:
    def __init__(self, plugins: list[EvidencePlugin] | None = None) -> None:
        self.plugins = plugins or []

    def run(self, context: DecisionContext) -> dict[str, Any]:
        results: dict[str, Any] = {}

        for plugin in self.plugins:
            try:
                results[plugin.name] = plugin.build(context)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Evidence plugin %s failed: %s",
                    plugin.name,
                    exc,
                )

                results[plugin.name] = {
                    "available": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

        return results
