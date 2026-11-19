import hashlib
import json

import pytest

from nse_quant.data_platform.native_p5_expansion_complete import (
    VERSION,
    complete_p5_expansion,
    replay_p5_expansion,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _expansion(underlying="NIFTY"):
    return {
        "version": "native-multi-underlying-expansion@1",
        "valid": True,
        "canonical_underlying": underlying,
        "derivative": {
            "binding": "canonical_underlying_to_derivative",
            "revision_id": "a" * 64,
            "recording_fingerprint": "b" * 64,
        },
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
    }


def _kwargs(**overrides):
    values = {
        "strategy_kind": "stock_option",
        "expansion_kind": "stock_options",
        "instrument_symbol": "RELIANCE",
        "acceptance_id": "p5-acceptance-001",
        "explicit_p5_acceptance_request": True,
    }
    values.update(overrides)
    return values


def test_completes_p5_expansion():
    expansion = _expansion()
    result = complete_p5_expansion(expansion, **_kwargs())
    assert result["p5_expansion_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    envelope = result["completed"]
    assert envelope["completed"] is True
    assert envelope["stock_options_supported"] is True
    assert envelope["stocks_supported"] is True
    assert envelope["spreads_supported"] is True
    assert envelope["multi_leg_strategies_supported"] is True
    assert envelope["strategy_kind"] == "stock_option"
    assert envelope["expansion_kind"] == "stock_options"
    assert envelope["instrument_symbol"] == "RELIANCE"
    assert envelope["acceptance_id"] == "p5-acceptance-001"
    assert envelope["explicit_p5_acceptance_request"] is True
    assert envelope["native_gates_open"] is True
    assert envelope["production_cutover_authorized"] is False
    assert envelope["live_trading_authorized"] is False
    assert envelope["deleted"] is False
    assert envelope["healed"] is False
    assert result["p5_expansion_fingerprint"] == hashlib.sha256(_canonical(envelope)).hexdigest()
    replayed = replay_p5_expansion(result)
    assert replayed["p5_expansion_replayed"] is True
    assert replayed["completed"] is True
    assert replayed["stock_options_supported"] is True
    assert replayed["stocks_supported"] is True
    assert replayed["spreads_supported"] is True
    assert replayed["multi_leg_strategies_supported"] is True
    assert replayed["deleted"] is False
    assert replayed["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"strategy_kind": "unknown"}, "P5_STRATEGY_KIND_INVALID"),
        ({"expansion_kind": "unknown"}, "P5_EXPANSION_KIND_INVALID"),
        ({"instrument_symbol": ""}, "P5_INSTRUMENT_SYMBOL_REQUIRED"),
        ({"acceptance_id": ""}, "P5_ACCEPTANCE_ID_REQUIRED"),
        ({"explicit_p5_acceptance_request": False}, "EXPLICIT_P5_ACCEPTANCE_REQUEST_REQUIRED"),
    ],
)
def test_rejects_invalid_expansion_inputs(overrides, error):
    with pytest.raises(Rejected) as exc:
        complete_p5_expansion(_expansion(), **_kwargs(**overrides))
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda value: value.update({"point_in_time_decision": True}),
            "POINT_IN_TIME_DECISION",
        ),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "P5_EXPANSION_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"version": "wrong"}),
            "P5_EXPANSION_VERSION_MISMATCH",
        ),
        (lambda value: value.update({"valid": False}), "P5_EXPANSION_NOT_VALID"),
        (
            lambda value: value.update({"canonical_underlying": "UNKNOWN"}),
            "P5_EXPANSION_CANONICAL_UNDERLYING_INVALID",
        ),
        (
            lambda value: value.update({"derivative": None}),
            "P5_EXPANSION_DERIVATIVE_REQUIRED",
        ),
        (
            lambda value: value["derivative"].update({"binding": "invalid"}),
            "P5_EXPANSION_DERIVATIVE_BINDING_INVALID",
        ),
        (
            lambda value: value["derivative"].update({"revision_id": "short"}),
            "P5_EXPANSION_DERIVATIVE_EVIDENCE_INVALID",
        ),
    ],
)
def test_rejects_forbidden_expansion_inputs(mutation, error):
    value = _expansion()
    mutation(value)
    with pytest.raises(Rejected) as exc:
        complete_p5_expansion(value, **_kwargs())
    assert exc.value.args[0] == error


@pytest.mark.parametrize(
    "mutation,error",
    [
        (
            lambda value: value.update({"point_in_time_decision": True}),
            "POINT_IN_TIME_DECISION",
        ),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "P5_COMPLETION_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"p5_expansion_completed": False}),
            "P5_COMPLETION_INCOMPLETE",
        ),
        (
            lambda value: value.update({"p5_expansion_fingerprint": "short"}),
            "P5_COMPLETION_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"p5_expansion_fingerprint": "0" * 64}),
            "P5_COMPLETION_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["completed"].update({"healed": True}),
            "P5_COMPLETION_HEALING_FORBIDDEN",
        ),
        (
            lambda value: value["completed"].update({"deleted": True}),
            "P5_COMPLETION_DELETION_FORBIDDEN",
        ),
        (
            lambda value: value["completed"].update({"stock_options_supported": False}),
            "P5_STOCK_OPTIONS_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"stocks_supported": False}),
            "P5_STOCKS_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"spreads_supported": False}),
            "P5_SPREADS_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"multi_leg_strategies_supported": False}),
            "P5_MULTI_LEG_STRATEGIES_NOT_SUPPORTED",
        ),
        (
            lambda value: value["completed"].update({"explicit_p5_acceptance_request": False}),
            "EXPLICIT_P5_ACCEPTANCE_REQUEST_REQUIRED",
        ),
        (
            lambda value: value["completed"].update({"native_gates_open": False}),
            "P5_NATIVE_GATES_NOT_OPEN",
        ),
    ],
)
def test_rejects_forbidden_replay_inputs(mutation, error):
    value = complete_p5_expansion(_expansion(), **_kwargs())
    mutation(value)
    with pytest.raises(Rejected) as exc:
        replay_p5_expansion(value)
    assert exc.value.args[0] == error
