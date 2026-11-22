from nse_quant.core.evidence import EvidenceMode, EvidencePluginConfig, EvidencePolicy


def test_default_plugin_mode_is_observation() -> None:
    policy = EvidencePolicy()

    assert policy.mode_for("multi_timeframe") is EvidenceMode.OBSERVATION
    assert not policy.can_gate("multi_timeframe")
    assert not policy.can_size("multi_timeframe")


def test_disabled_plugin_cannot_gate_or_size() -> None:
    policy = EvidencePolicy(
        plugins={
            "event_risk": EvidencePluginConfig(
                enabled=False,
                mode=EvidenceMode.HARD_GATE,
            )
        }
    )

    assert policy.mode_for("event_risk") is EvidenceMode.OBSERVATION
    assert not policy.can_gate("event_risk")
    assert not policy.can_size("event_risk")


def test_hard_gate_plugin_can_gate_but_not_size() -> None:
    policy = EvidencePolicy(plugins={"event_risk": EvidencePluginConfig(mode=EvidenceMode.HARD_GATE)})

    assert policy.can_gate("event_risk")
    assert not policy.can_size("event_risk")


def test_risk_sizing_plugin_can_size_but_not_gate() -> None:
    policy = EvidencePolicy(plugins={"option_positioning": EvidencePluginConfig(mode=EvidenceMode.RISK_SIZING)})

    assert policy.can_size("option_positioning")
    assert not policy.can_gate("option_positioning")
