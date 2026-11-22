"""Canonical 108-regime institutional registry.

Sources: docs/strategies/108-regime-strategy-playbook.md,
docs/strategies/IRON_CONDOR_MASTER_MANUAL.md, and the implementation charter.

The regime has exactly four components: IV state, term structure, skew, and
price action. RV, VRP, and multi-timeframe trend are separate evidence.
Registry v2 uses the charter's strong-trend spelling without legacy aliases.
Historical artifacts must retain their original version and must not be
silently relabelled.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import product

REGIME_REGISTRY_VERSION = "institutional_regime_registry_v2"
PLAYBOOK_SOURCE = "docs/strategies/108-regime-strategy-playbook.md"


class IvState(StrEnum):
    HIGH_IV = "HIGH_IV"
    LOW_IV = "LOW_IV"


class TermStructure(StrEnum):
    CONTANGO = "CONTANGO"
    FLAT_TERM = "FLAT_TERM"
    BACKWARDATION = "BACKWARDATION"


class Skew(StrEnum):
    NORMAL_SKEW = "NORMAL_SKEW"
    HIGH_PUT_SKEW = "HIGH_PUT_SKEW"
    FORWARD_REVERSE_SKEW = "FORWARD_REVERSE_SKEW"


class PriceAction(StrEnum):
    STRONG_BULL_TREND = "STRONG_BULL_TREND"
    STRONG_BEAR_TREND = "STRONG_BEAR_TREND"
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

# Only the six playbook iron-condor cells; backwardation is excluded.
IRON_CONDOR_REGIME_IDS: tuple[str, ...] = ("H06", "H12", "H18", "H24", "H30", "H36")
IRON_CONDOR_REGIMES: frozenset[str] = frozenset(REGIMES_BY_ID[i].label for i in IRON_CONDOR_REGIME_IDS)


def is_canonical_regime_label(label: object) -> bool:
    """Accept only an exact, complete four-component canonical label."""
    return isinstance(label, str) and label in REGIMES


def get_regime(label: str) -> RegimeDefinition:
    """Return the canonical definition or raise ValueError."""
    try:
        return REGIMES[label]
    except KeyError:
        raise ValueError(f"Not a canonical institutional regime label: {label!r}") from None


def validate_regime_labels(labels: object, *, context: str) -> list[str]:
    """Validate every label without coercing or translating legacy labels."""
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
