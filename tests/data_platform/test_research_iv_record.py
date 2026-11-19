"""Pure archive identity/encoding contracts, not native source/audit integration."""

import pytest

from nse_quant.data_platform.research_iv_record import (
    build_id,
    canonical,
    checked_json,
    input_id,
    validate_prior_links,
)

A, B, C, D = (x * 64 for x in "abcd")


def test_input_roles_terms_and_definition_all_bound():
    first = input_id(A, B, C, D)
    assert first != input_id(B, A, C, D)
    assert first != input_id(A, B, D, D)
    assert first != input_id(A, B, C, C)
    assert build_id(first, canonical({"status": "review_required"})) != build_id(
        first, canonical({"status": "research_iv_candidate"})
    )


@pytest.mark.parametrize("pins", [(A, A, C, D), ("A" * 64, B, C, D), (A, B, None, D)])
def test_no_invalid_input_identity(pins):
    with pytest.raises(ValueError):
        input_id(*pins)


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"a":NaN}',
        '{"a":Infinity}',
        '{"a":1}\n',
        ' {"a":1}',
        "[]",
        "{}{}",
        "not-json",
    ],
)
def test_strict_complete_record_bytes(raw):
    with pytest.raises(ValueError):
        checked_json(raw)


def test_valid_json_and_byte_limit():
    assert checked_json('{"a":1}') == {"a": 1}
    with pytest.raises(ValueError, match="BYTE_LIMIT"):
        checked_json('{"a":1}', 2)


def test_prior_evidence_links_are_exact_and_ordered():
    validate_prior_links("[]", ())
    validate_prior_links(canonical([A, B]), (A, B))
    with pytest.raises(ValueError, match="ALL_PRIOR"):
        validate_prior_links(canonical([B, A]), (A, B))
    with pytest.raises(ValueError):
        validate_prior_links(canonical([A]), (A, B))
    with pytest.raises(ValueError):
        validate_prior_links(canonical([A, A]), (A, A))


def test_payload_changes_identity_but_exact_retry_does_not():
    group = input_id(A, B, C, D)
    raw = canonical({"option_event_ts": None, "premium": "1.20"})
    assert build_id(group, raw) == build_id(group, raw)
    assert build_id(group, raw) != build_id(group, canonical({"premium": "1.2"}))
