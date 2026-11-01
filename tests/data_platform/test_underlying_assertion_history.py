"""Pure history/lifecycle evidence rules, not native recording or identity verification."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nse_quant.data_platform import underlying_assertion_history as history

T = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "graph",
    [
        {},
        {"a": ("a",)},
        {"a": ("b",)},
        {"a": (), "b": ()},
        {"a": ("b",), "b": ("a",)},
        {"a": (), "b": ("a", "a")},
        {"a": (), "b": ("a",), "c": ("b",)},
    ],
)
def test_incomplete_or_cyclic_evidence_never_selects_old_good(graph):
    with pytest.raises(history.AssertionReviewRequired):
        history.history_last(graph)


def test_all_prior_history_order_is_not_hash_or_clock_order():
    assert history.history_last({"z": (), "a": ("z",), "m": ("a", "z")}) == "m"


@pytest.mark.parametrize(
    "states,outcome",
    [
        (("PLANNED",), "INCOMPLETE"),
        (("PLANNED", "RUNNING"), "INCOMPLETE"),
        (("PLANNED", "FAILED"), "FAILED"),
        (("PLANNED", "CANCELLED"), "CANCELLED"),
        (("PLANNED", "RUNNING", "FAILED"), "FAILED"),
        (("PLANNED", "RUNNING", "CANCELLED"), "CANCELLED"),
        (("PLANNED", "RUNNING", "SUCCEEDED"), "SUCCEEDED"),
    ],
)
def test_full_recording_lifecycles(states, outcome):
    rows = [(i + 1, state, T, None) for i, state in enumerate(states)]
    assert history.lifecycle(rows) == outcome


@pytest.mark.parametrize(
    "states",
    [
        (),
        ("SUCCEEDED",),
        ("PLANNED", "SUCCEEDED"),
        ("RUNNING", "SUCCEEDED"),
        ("PLANNED", "RUNNING", "STAGED"),
        ("PLANNED", "RUNNING", "SUCCEEDED", "FAILED"),
    ],
)
def test_latest_success_or_unsupported_phases_not_enough(states):
    with pytest.raises(history.AssertionReviewRequired):
        history.lifecycle([(i + 1, state, T, None) for i, state in enumerate(states)])


@pytest.mark.parametrize("index", [True, 0, 2, "1"])
def test_event_index_type_and_contiguity(index):
    with pytest.raises(history.AssertionReviewRequired):
        history.lifecycle([(index, "PLANNED", T, None)])


def test_success_has_no_reason_and_naive_clocks_fail():
    with pytest.raises(history.AssertionReviewRequired):
        history.lifecycle(
            [
                (1, "PLANNED", T, None),
                (2, "RUNNING", T, None),
                (3, "SUCCEEDED", T, "EXECUTION_ERROR"),
            ]
        )
    with pytest.raises(history.AssertionReviewRequired):
        history.lifecycle([(1, "PLANNED", T.replace(tzinfo=None), None)])


def test_clock_normalizes_instants_without_inventing_source_time():
    local = T.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert history.instant(T) == history.instant(local)
    assert history.canonical([T]) == history.canonical([local])
