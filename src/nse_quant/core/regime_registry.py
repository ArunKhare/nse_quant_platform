"""Canonical 108-regime institutional registry.

Sources of truth (charter section 2):

- ``docs/strategies/108-regime-strategy-playbook.md``: the 108 cards (H01-H54,
  L01-L54), their descriptive regimes, and the recommended strategy per card.
- ``docs/strategies/IRON_CONDOR_MASTER_MANUAL.md``: the systematic label
  spelling (``FLAT_TERM``, ``HIGH_PUT_SKEW``, ``FORWARD_REVERSE_SKEW``) and the
  six iron-condor regimes.
- ``docs/strategies/framework-foundations-quantitative-measurement.md``: the
  four structural dimensions.

The canonical institutional regime has exactly four components::

    IV state x term structure x skew x price action

Labels are generated from the component vocabularies below in playbook card
order, so no label is hand-typed. Realized volatility, variance risk premium,
and multi-timeframe trend are never regime components and must not be
appended to a label.

Note: an earlier playbook draft (``INFO/108-regime-strategy-playbook-v2.md``,
not in this repository) printed all 36 FORWARD_REVERSE_SKEW label codes as
``..._FORWARD_REVERSE_SKEW_REVERSE_SKEW``. Those malformed codes are rejected.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import product

REGIME_REGISTRY_VERSION = "institutional_regime_registry_v1"
PLAYBOOK_SOURCE = "docs/strategies/108-regime-strategy-playbook.md"


class IvState(StrEnum):
    HIGH_IV = "HIGH_IV"
    LOW_IV = "LOW_IV"  # playbook: "Normal / Low IV" (IVR < 70)


class TermStructure(StrEnum):
    CONTANGO = "CONTANGO"
    FLAT_TERM = "FLAT_TERM"
    BACKWARDATION = "BACKWARDATION"


class Skew(StrEnum):
    NORMAL_SKEW = "NORMAL_SKEW"
    HIGH_PUT_SKEW = "HIGH_PUT_SKEW"  # playbook: "Steep Downside Skew"
    FORWARD_REVERSE_SKEW = "FORWARD_REVERSE_SKEW"


class PriceAction(StrEnum):
    STRONG_BULL = "STRONG_BULL"
    STRONG_BEAR = "STRONG_BEAR"
    RANGE_HIGH = "RANGE_HIGH"
    RANGE_LOW = "RANGE_LOW"
    COMPRESSION = "COMPRESSION"
    HIGH_VOL_CHOP = "HIGH_VOL_CHOP"


@dataclass(frozen=True)
class RegimeDefinition:
    regime_id: str
    label: str
    iv_state: IvState
    term_structure: TermStructure
    skew: Skew
    price_action: PriceAction


def _build_registry() -> dict[str, RegimeDefinition]:
    registry: dict[str, RegimeDefinition] = {}
    for iv_state in IvState:
        prefix = "H" if iv_state is IvState.HIGH_IV else "L"
        combos = product(TermStructure, Skew, PriceAction)
        for index, (term, skew, price_action) in enumerate(combos, start=1):
            label = f"{iv_state}_{term}_{skew}_{price_action}"
            registry[label] = RegimeDefinition(
                regime_id=f"{prefix}{index:02d}",
                label=label,
                iv_state=iv_state,
                term_structure=term,
                skew=skew,
                price_action=price_action,
            )
    return registry


REGIMES: dict[str, RegimeDefinition] = _build_registry()
REGIMES_BY_ID: dict[str, RegimeDefinition] = {r.regime_id: r for r in REGIMES.values()}

# Playbook "Top Recommended Strategy: Asymmetric defined-risk iron condor":
# exactly H06, H12, H18, H24, H30, H36 (High IV, Contango or Flat term, any skew,
# High-vol chop). Backwardation chop (H42/H48/H54) and all Low IV chop regimes
# are explicitly excluded by the playbook and the iron-condor master manual.
IRON_CONDOR_REGIME_IDS: tuple[str, ...] = ("H06", "H12", "H18", "H24", "H30", "H36")
IRON_CONDOR_REGIMES: frozenset[str] = frozenset(REGIMES_BY_ID[i].label for i in IRON_CONDOR_REGIME_IDS)


def is_canonical_regime_label(label: object) -> bool:
    """Return True only for an exact, complete four-component canonical label."""
    return isinstance(label, str) and label in REGIMES


def get_regime(label: str) -> RegimeDefinition:
    """Return the definition for a canonical label; raise ValueError otherwise."""
    try:
        return REGIMES[label]
    except KeyError:
        raise ValueError(f"Not a canonical institutional regime label: {label!r}") from None


def validate_regime_labels(labels: object, *, context: str) -> list[str]:
    """Validate that every label is canonical; return them unchanged."""
    if labels is None:
        return []
    if isinstance(labels, str):
        values: list[object] = [labels]
    elif isinstance(labels, Iterable):
        values = list(labels)
    else:
        raise TypeError(f"{context}: regime labels must be a string or iterable")
    invalid = sorted({str(label) for label in values if not is_canonical_regime_label(label)})
    if invalid:
        raise ValueError(
            f"{context}: non-canonical regime labels {invalid}; "
            f"labels must come from {REGIME_REGISTRY_VERSION} ({PLAYBOOK_SOURCE})"
        )
    return [str(label) for label in values]
