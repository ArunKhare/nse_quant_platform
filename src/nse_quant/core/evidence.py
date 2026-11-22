"""Evidence-plugin governance contracts.

Every evidence plugin must declare an explicit runtime role. This prevents a
plugin from silently changing from observation-only evidence into an entry
gate or risk-sizing input.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceMode(StrEnum):
    """Runtime authority granted to an evidence plugin."""

    OBSERVATION = "observation"
    RISK_SIZING = "risk_sizing"
    HARD_GATE = "hard_gate"


class EvidencePluginConfig(BaseModel):
    """Configuration for one evidence plugin."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mode: EvidenceMode = EvidenceMode.OBSERVATION
    max_age_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Maximum acceptable evidence age; None uses the plugin default.",
    )
    manual_override_allowed: bool = True
    override_reason_required: bool = True


class EvidencePolicy(BaseModel):
    """Runtime evidence-policy contract."""

    model_config = ConfigDict(extra="forbid")

    plugins: dict[str, EvidencePluginConfig] = Field(default_factory=dict)

    def mode_for(self, plugin_name: str) -> EvidenceMode:
        """Return the configured mode for a plugin.

        Disabled plugins are observation-only: they may still produce evidence,
        but they cannot gate or size a decision.
        """
        plugin = self.plugins.get(plugin_name)
        if plugin is None or not plugin.enabled:
            return EvidenceMode.OBSERVATION
        return plugin.mode

    def can_gate(self, plugin_name: str) -> bool:
        return self.mode_for(plugin_name) is EvidenceMode.HARD_GATE

    def can_size(self, plugin_name: str) -> bool:
        return self.mode_for(plugin_name) is EvidenceMode.RISK_SIZING
