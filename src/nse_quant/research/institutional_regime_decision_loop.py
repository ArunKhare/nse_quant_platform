"""Decision-loop integration for the institutional regime plugin.

Registers InstitutionalRegimePlugin into the evidence plugin runner so regime
evidence is produced per decision cycle. Observational only; never grants
decision eligibility or enables live trading.
"""

from __future__ import annotations

from typing import Any

from nse_quant.research.evidence_plugins.base import EvidencePlugin
from nse_quant.research.evidence_plugins.institutional_regime import (
    InstitutionalRegimePlugin,
)


def build_institutional_regime_plugin(
    *,
    store: Any,
    settings: Any,
) -> EvidencePlugin:
    """Construct the institutional regime plugin for decision-loop registration."""
    return InstitutionalRegimePlugin(store=store, settings=settings)


def register_institutional_regime(
    *,
    plugins: list[EvidencePlugin],
    store: Any,
    settings: Any,
) -> list[EvidencePlugin]:
    """Append the institutional regime plugin to an existing plugin list."""
    plugin = build_institutional_regime_plugin(store=store, settings=settings)
    if any(existing.name == plugin.name for existing in plugins):
        return plugins
    plugins.append(plugin)
    return plugins
