"""Settings and integration coverage for event-impact mapping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nse_quant.core.settings import (
    EventImpactSettings,
    EvidencePluginsSettings,
)
from nse_quant.research.evidence_plugins.event_impact import EventImpactMapper


def test_event_impact_is_disabled_by_default() -> None:
    plugins = EvidencePluginsSettings()

    assert plugins.event_impact.enabled is False
    assert plugins.event_impact.blackout_minutes_before == 30
    assert plugins.event_impact.blackout_minutes_after == 30


def test_event_impact_accepts_explicit_configuration() -> None:
    plugins = EvidencePluginsSettings(
        event_impact=EventImpactSettings(
            enabled=True,
            blackout_minutes_before=45,
            blackout_minutes_after=15,
        )
    )

    assert plugins.event_impact.enabled is True
    assert plugins.event_impact.blackout_minutes_before == 45
    assert plugins.event_impact.blackout_minutes_after == 15


@pytest.mark.parametrize(
    ("before", "after"),
    [(-1, 0), (0, -1)],
)
def test_negative_blackout_windows_are_rejected(before: int, after: int) -> None:
    with pytest.raises(ValidationError):
        EventImpactSettings(
            blackout_minutes_before=before,
            blackout_minutes_after=after,
        )


def test_mapper_is_plugin_named_event_impact() -> None:
    assert EventImpactMapper.name == "event_impact"
