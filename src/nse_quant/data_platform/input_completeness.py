"""Input completeness validation for native strategy/analytics inputs.

Validates a dict of supplied inputs against the 9 requirements in
native_strategy_requirements.py, returning which are present/missing, without
granting eligibility or enabling live trading. Addresses the "complete required
native strategy/analytics inputs" sub-gap of gate 6 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_requirements import REQUIREMENTS

REQUIRED_KEYS = tuple(name for name, _, _ in REQUIREMENTS)


def validate_input_completeness(
    *,
    supplied_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Validate completeness of supplied inputs against the 9 requirements."""
    if type(supplied_inputs) is not dict:
        return dict(
            complete=False,
            reason="SUPPLIED_INPUTS_OBJECT_REQUIRED",
            present=[],
            missing=list(REQUIRED_KEYS),
        )

    present = [key for key in REQUIRED_KEYS if key in supplied_inputs]
    missing = [key for key in REQUIRED_KEYS if key not in supplied_inputs]
    complete = not missing
    return dict(
        complete=complete,
        reason="ALL_REQUIRED_INPUTS_PRESENT" if complete else "MISSING_REQUIRED_INPUTS",
        present=present,
        missing=missing,
    )
