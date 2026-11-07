"""Tests for institutional regime decision-loop integration."""

from __future__ import annotations

from nse_quant.research.evidence_plugins.base import EvidencePlugin
from nse_quant.research.institutional_regime_decision_loop import (
    build_institutional_regime_plugin,
    register_institutional_regime,
)


class _Settings:
    pass


class _Store:
    pass


def test_build_plugin():
    plugin = build_institutional_regime_plugin(store=_Store(), settings=_Settings())
    assert plugin.name == "institutional_regime"
    assert isinstance(plugin, EvidencePlugin)


def test_register_appends():
    plugins: list[EvidencePlugin] = []
    result = register_institutional_regime(plugins=plugins, store=_Store(), settings=_Settings())
    assert len(result) == 1
    assert result[0].name == "institutional_regime"


def test_register_idempotent():
    plugins: list[EvidencePlugin] = []
    register_institutional_regime(plugins=plugins, store=_Store(), settings=_Settings())
    result = register_institutional_regime(plugins=plugins, store=_Store(), settings=_Settings())
    assert len(result) == 1
