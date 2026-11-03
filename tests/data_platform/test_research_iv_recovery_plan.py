"""Pure reconciliation policy tests; no native computation substitutions."""

import pytest

from nse_quant.data_platform.research_iv_recovery_plan import classify_recovery_entries

PIN = "a" * 64
NAME = PIN + ".research-iv.json"


def classify(entries):
    return classify_recovery_entries(entries, bound_name=NAME, bound_sha256=PIN, bound_size=12)


def test_exact_bound_entry_retained():
    result = classify((("b" * 64, NAME, "PINNED_BYTES_UNASSESSED", 12, PIN, True),))
    assert result[0].disposition == "RECORDED_ARTIFACT_RETAIN"


@pytest.mark.parametrize(
    "index,value",
    [(2, "ARTIFACT_PIN_MISMATCH_REVIEW"), (3, 11), (4, "c" * 64), (5, False)],
    ids=["kind", "size", "digest", "pin"],
)
def test_bound_mismatch_never_retained(index, value):
    entry = ["b" * 64, NAME, "PINNED_BYTES_UNASSESSED", 12, PIN, True]
    entry[index] = value
    assert classify((tuple(entry),))[0].disposition == "BOUND_ARTIFACT_REVIEW"


def test_other_artifact_not_declared_orphan():
    result = classify(
        (("b" * 64, "c" * 64 + ".research-iv.json", "PINNED_BYTES_UNASSESSED", 12, "c" * 64, True),)
    )
    assert result[0].disposition == "OUTSIDE_REVIEWED_BINDING_OWNERSHIP_UNKNOWN"


@pytest.mark.parametrize(
    "kind",
    [
        "PENDING_REMNANT_REVIEW",
        "FOREIGN_ENTRY_REVIEW",
        "NONREGULAR_ENTRY_REVIEW",
        "REDIRECT_REVIEW",
    ],
)
def test_unresolved_entries_retained(kind):
    result = classify((("b" * 64, None, kind, 0, None, False),))
    assert result[0].disposition == "UNRESOLVED_ENTRY_RETAIN_FOR_REVIEW"


def test_bounds_and_duplicates():
    entry = ("b" * 64, None, "FOREIGN_ENTRY_REVIEW", 0, None, False)
    with pytest.raises(ValueError, match="DUPLICATE"):
        classify((entry, entry))
    with pytest.raises(ValueError, match="LIMIT"):
        classify((entry,) * 257)
    assert classify(()) == ()
