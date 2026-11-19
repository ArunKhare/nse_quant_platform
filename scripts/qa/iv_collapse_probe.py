"""Opt-in observation of the real IV-collapse evaluation; never changes results."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterator
from typing import Any

import pytest


def numeric(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def reason(value: object) -> str | None:
    text = getattr(value, "value", None)
    return text if isinstance(text, str) else None


def observation(frame: Any, result: Any) -> dict[str, object]:
    local = frame.f_locals
    features = local.get("features")
    engine = local.get("self")
    settings = getattr(engine, "exit_settings", None)
    position = local.get("strategy_position")
    rank = numeric(getattr(features, "iv_rank", None))
    atm = numeric(getattr(features, "atm_iv", None))
    threshold = numeric(getattr(settings, "iv_collapse_pct", None))
    return {
        "atm_iv": atm,
        "iv_rank": rank,
        "iv_collapse_pct": threshold,
        "iv_predicate": (
            atm is not None and rank is not None and threshold is not None and rank < threshold
        ),
        "entry_price": numeric(getattr(position, "entry_price", None)),
        "current_price": numeric(getattr(position, "current_price", None)),
        "triggered_reasons": [reason(item) for item in getattr(result, "triggered_reasons", ())],
        "selected_reason": reason(getattr(result, "selected_reason", None)),
    }


@pytest.fixture(autouse=True)
def observe_iv_collapse(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.name != "test_position_closes_on_iv_collapse":
        yield
        return
    if sys.getprofile() is not None:
        pytest.fail("IV probe refuses to replace an existing profiler")
    records: list[dict[str, object]] = []

    def profile(frame: Any, event: str, arg: Any) -> None:
        if (
            event == "return"
            and frame.f_code.co_name == "evaluate"
            and frame.f_globals.get("__name__") == "nse_quant.strategy.exit_engine"
        ):
            records.append(observation(frame, arg))

    sys.setprofile(profile)
    try:
        yield
    finally:
        sys.setprofile(None)
        request.node.add_report_section(
            "teardown",
            "iv-collapse-observations",
            json.dumps(
                {"evaluation_count": len(records), "evaluations": records},
                sort_keys=True,
                allow_nan=False,
            ),
        )
