import pytest

from nse_quant.data_platform.reference_supersession import AssessmentNode, resolve_supersession

A, B, C, GROUP = "a" * 64, "b" * 64, "c" * 64, "1" * 64


def node(revision, supersedes=(), group=GROUP):
    return AssessmentNode(revision, group, supersedes)


def test_exact_active_pin():
    assert resolve_supersession((node(A),), A).reason_code == "ACTIVE_PINNED_ASSESSMENT"


def test_later_quarantine_not_filtered_before_supersession():
    graph = (node(A), node(B, (A,)))
    assert resolve_supersession(graph, A).reason_code == "ASSESSMENT_SUPERSEDED"
    assert resolve_supersession(graph, B).active_revision_ids == (B,)


@pytest.mark.parametrize(
    "graph,pin,reason",
    [
        ((), A, "ASSESSMENT_NOT_FOUND"),
        ((node(A),), "bad", "INVALID_ASSESSMENT_PIN"),
        ((node(A),), B, "ASSESSMENT_NOT_FOUND"),
        ((node(A), node(A)), A, "DUPLICATE_ASSESSMENT_IDENTITY"),
        ((node(A), node(B, group="2" * 64)), A, "MIXED_INPUT_REVISIONS"),
        ((node(A, (A,)),), A, "SUPERSESSION_CYCLE"),
        ((node(A, (B,)), node(B, (A,))), A, "SUPERSESSION_CYCLE"),
        ((node(A, (B,)),), A, "DANGLING_SUPERSESSION_LINK"),
        ((node(A), node(B)), A, "AMBIGUOUS_ACTIVE_ASSESSMENTS"),
        ((node(A), node(B, (A, A))), B, "DUPLICATE_SUPERSESSION_LINK"),
        ((node(A, ("bad",)),), A, "INVALID_SUPERSESSION_LINK"),
        ((node("bad"),), A, "INVALID_ASSESSMENT_IDENTITY"),
    ],
)
def test_fail_closed_graphs(graph, pin, reason):
    assert resolve_supersession(graph, pin).reason_code == reason


def test_full_ancestry_and_transitive_links():
    graph = (node(A), node(B, (A,)), node(C, (A, B)))
    assert resolve_supersession(graph, C).reason_code == "ACTIVE_PINNED_ASSESSMENT"
    assert resolve_supersession(graph, B).reason_code == "ASSESSMENT_SUPERSEDED"


def test_deep_history_is_iterative_and_bounded(monkeypatch):
    ids = [f"{i:064x}" for i in range(1001)]
    graph = tuple(node(key, (ids[i - 1],) if i else ()) for i, key in enumerate(ids))
    assert resolve_supersession(graph, ids[-1]).reason_code == "ACTIVE_PINNED_ASSESSMENT"
    import nse_quant.data_platform.reference_supersession as module

    monkeypatch.setattr(module, "MAX_ASSESSMENTS", 2)
    assert resolve_supersession(graph, ids[-1]).reason_code == "ASSESSMENT_HISTORY_LIMIT"
