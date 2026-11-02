"""Pure diagnostic projection checks, not native strategy verification."""

from types import SimpleNamespace

from scripts.qa.iv_collapse_probe import numeric, observation


def test_numeric_rejects_nonfinite_and_boolean() -> None:
    for value in (True, False, float("nan"), float("inf"), "0.2", None):
        assert numeric(value) is None
    assert numeric(0.2) == 0.2


def test_projection_retains_actual_reason_and_strict_boundary() -> None:
    frame = SimpleNamespace(
        f_locals={
            "features": SimpleNamespace(atm_iv=0.12, iv_rank=20.0),
            "self": SimpleNamespace(exit_settings=SimpleNamespace(iv_collapse_pct=20.0)),
            "strategy_position": SimpleNamespace(entry_price=100.0, current_price=90.0),
        }
    )
    result = SimpleNamespace(
        triggered_reasons=[SimpleNamespace(value="IV_COLLAPSE")],
        selected_reason=SimpleNamespace(value="IV_COLLAPSE"),
    )
    record = observation(frame, result)
    assert record["iv_predicate"] is False
    assert record["selected_reason"] == "IV_COLLAPSE"
    frame.f_locals["features"].iv_rank = 19.0
    assert observation(frame, result)["iv_predicate"] is True
    frame.f_locals["features"].atm_iv = None
    assert observation(frame, result)["iv_predicate"] is False


def test_missing_fields_remain_unknown() -> None:
    record = observation(SimpleNamespace(f_locals={}), None)
    assert record["atm_iv"] is None
    assert record["iv_rank"] is None
    assert record["selected_reason"] is None
    assert record["iv_predicate"] is False
