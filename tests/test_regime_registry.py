"""Canonical registry and exact iron-condor allowlist contract tests."""

from __future__ import annotations

import pytest

from nse_quant.core.regime_registry import (
    IRON_CONDOR_REGIMES,
    REGIME_REGISTRY_VERSION,
    REGIMES,
    REGIMES_BY_ID,
    PriceAction,
    TermStructure,
    get_regime,
    is_canonical_regime_label,
    validate_regime_labels,
)
from nse_quant.core.settings import Settings, get_settings

EXPECTED_IRON_CONDOR = {
    "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP",
    "HIGH_IV_CONTANGO_HIGH_PUT_SKEW_HIGH_VOL_CHOP",
    "HIGH_IV_CONTANGO_FORWARD_REVERSE_SKEW_HIGH_VOL_CHOP",
    "HIGH_IV_FLAT_TERM_NORMAL_SKEW_HIGH_VOL_CHOP",
    "HIGH_IV_FLAT_TERM_HIGH_PUT_SKEW_HIGH_VOL_CHOP",
    "HIGH_IV_FLAT_TERM_FORWARD_REVERSE_SKEW_HIGH_VOL_CHOP",
}


def test_registry_has_exactly_108_unique_four_component_labels():
    assert len(REGIMES) == 108
    assert len(REGIMES_BY_ID) == 108
    for definition in REGIMES.values():
        assert definition.label == "_".join(
            [
                definition.iv_state,
                definition.term_structure,
                definition.skew,
                definition.price_action,
            ]
        )


def test_registry_v2_uses_charter_price_actions_without_aliases():
    assert REGIME_REGISTRY_VERSION == "institutional_regime_registry_v2"
    assert set(PriceAction.__members__) == {
        "STRONG_BULL_TREND",
        "STRONG_BEAR_TREND",
        "RANGE_HIGH",
        "RANGE_LOW",
        "COMPRESSION",
        "HIGH_VOL_CHOP",
    }
    assert len(PriceAction.__members__) == len(PriceAction)


@pytest.mark.parametrize(
    "regime_id,label",
    [
        ("H01", "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL_TREND"),
        ("H02", "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BEAR_TREND"),
        ("H06", "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"),
        ("H18", "HIGH_IV_CONTANGO_FORWARD_REVERSE_SKEW_HIGH_VOL_CHOP"),
        ("H42", "HIGH_IV_BACKWARDATION_NORMAL_SKEW_HIGH_VOL_CHOP"),
        ("H54", "HIGH_IV_BACKWARDATION_FORWARD_REVERSE_SKEW_HIGH_VOL_CHOP"),
        ("L01", "LOW_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL_TREND"),
        ("L02", "LOW_IV_CONTANGO_NORMAL_SKEW_STRONG_BEAR_TREND"),
        ("L54", "LOW_IV_BACKWARDATION_FORWARD_REVERSE_SKEW_HIGH_VOL_CHOP"),
    ],
)
def test_regime_ids_follow_playbook_card_order(regime_id, label):
    assert REGIMES_BY_ID[regime_id].label == label


def test_iron_condor_allowlist_is_exactly_the_six_playbook_regimes():
    assert IRON_CONDOR_REGIMES == EXPECTED_IRON_CONDOR
    for label in IRON_CONDOR_REGIMES:
        regime = get_regime(label)
        assert regime.price_action is PriceAction.HIGH_VOL_CHOP
        assert regime.term_structure is not TermStructure.BACKWARDATION
        assert regime.iv_state == "HIGH_IV"


@pytest.mark.parametrize(
    "label",
    [
        "BULL|NORMAL",
        "RANGE|HIGH",
        "BULLISH",
        "BEARISH",
        "MIXED",
        "HIGH_VOL_CHOP",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BEAR",
        "LOW_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL",
        "LOW_IV_CONTANGO_NORMAL_SKEW_STRONG_BEAR",
        "HIGH_IV_FLAT_NORMAL_SKEW_HIGH_VOL_CHOP",
        "NORMAL_IV_CONTANGO_NORMAL_SKEW_RANGE_MIDDLE",
        "HIGH_IV_CONTANGO_STEEP_DOWNSIDE_SKEW_HIGH_VOL_CHOP",
        "HIGH_IV_CONTANGO_FORWARD_REVERSE_SKEW_REVERSE_SKEW",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP_POSITIVE_VRP",
        "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP_BULLISH",
        "",
        None,
    ],
)
def test_non_canonical_labels_are_rejected(label):
    assert not is_canonical_regime_label(label)


def test_validate_regime_labels_raises_on_any_invalid_label():
    with pytest.raises(ValueError, match="non-canonical"):
        validate_regime_labels(["HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP", "BULL|NORMAL"], context="t")


def test_get_regime_does_not_translate_legacy_labels():
    with pytest.raises(ValueError, match="Not a canonical"):
        get_regime("HIGH_IV_CONTANGO_NORMAL_SKEW_STRONG_BULL")


def test_configured_iron_condor_allowlist_is_exact():
    profile = get_settings().get_strategy_profile("iron_condor_monitor")
    assert set(profile.regime_policy.allowed_regimes) == EXPECTED_IRON_CONDOR


def _settings_with_allowlist(allowed: list[str]) -> Settings:
    base = get_settings().model_dump(mode="python")
    base["strategies"]["iron_condor_monitor"]["regime_policy"]["allowed_regimes"] = allowed
    return Settings.model_validate(base)


@pytest.mark.parametrize(
    "allowed",
    [
        ["BULL|NORMAL"],
        ["HIGH_IV_BACKWARDATION_NORMAL_SKEW_HIGH_VOL_CHOP"],
        ["HIGH_IV_CONTANGO_NORMAL_SKEW_RANGE_HIGH"],
        ["LOW_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"],
    ],
)
def test_settings_reject_invalid_iron_condor_allowlist(allowed):
    with pytest.raises(ValueError):
        _settings_with_allowlist(allowed)
