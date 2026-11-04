"""Real cryptography causal-chain tests, not independent authority authentication."""

import json
from dataclasses import replace

import pytest
from key_lifecycle_fixture import arguments, event, key, public

from nse_quant.data_platform import observed_key_lifecycle as api


def test_rotation_possession_chain_and_terminal_revocation():
    root, second, third = key(), key(), key()
    first = event(root, second, root=root)
    later = event(second, third, root=root, sequence=2, predecessor=api.sha(first))
    result = api.inspect_key_lifecycle(**arguments((first, later), root))
    assert result.active_public_key_hex == public(third).hex()
    assert set(result.retired_key_sha256s) == {api.sha(public(root)), api.sha(public(second))}
    assert result.signed_causal_constraints_satisfied
    for name in (
        "root_authority_authenticated",
        "namespace_authority_verified",
        "global_history_completeness_verified",
        "key_currentness_verified",
        "authorized_revocation_asserted",
        "identity_verified",
        "availability_evidence_verified",
        "decision_eligibility_asserted",
    ):
        assert getattr(result, name) is False
    terminal = event(third, None, root=root, sequence=3, predecessor=api.sha(later))
    ended = api.inspect_key_lifecycle(**arguments((first, later, terminal), root))
    assert ended.active_public_key_hex is None
    assert ended.evidence_fingerprint != result.evidence_fingerprint
    assert api.inspect_key_lifecycle(**arguments((first, later, terminal), root)) == ended


@pytest.mark.parametrize(
    "kind",
    ["gap", "wrong-prev", "rollback", "fork", "omit-first"],
    ids=["gap", "wrong-prev", "rollback", "fork", "omit-first"],
)
def test_causal_failures_have_no_prefix_salvage(kind):
    root, second, third = key(), key(), key()
    first = event(root, second, root=root)
    later = event(second, third, root=root, sequence=2, predecessor=api.sha(first))
    records: tuple[bytes, ...] = (first, later)
    if kind == "gap":
        records = (first, event(second, third, root=root, sequence=3, predecessor=api.sha(first)))
    elif kind == "wrong-prev":
        records = (first, event(second, third, root=root, sequence=2, predecessor="0" * 64))
    elif kind == "rollback":
        records = (later, first)
    elif kind == "fork":
        records = (first, event(root, third, root=root))
    else:
        records = (later,)
    with pytest.raises(api.KeyLifecycleRejected, match="CAUSAL_CHAIN_MISMATCH"):
        api.inspect_key_lifecycle(**arguments(records, root))


def test_root_pin_namespace_and_asset_binding():
    root, second = key(), key()
    raw = event(root, second, root=root)
    args = arguments((raw,), root)
    args["expected_root_key_sha256"] = "0" * 64
    with pytest.raises(api.KeyLifecycleRejected, match="ROOT_PIN"):
        api.inspect_key_lifecycle(**args)
    for target in (
        replace(args["scope"], namespace="OTHER"),
        replace(args["scope"], asset_kind="EQUITY"),
    ):
        args = arguments((raw,), root)
        args["scope"] = target
        with pytest.raises(api.KeyLifecycleRejected, match="CAUSAL_CHAIN_MISMATCH"):
            api.inspect_key_lifecycle(**args)


@pytest.mark.parametrize(
    "field", ["signature_hex", "successor_signature_hex"], ids=["current", "successor"]
)
def test_actual_signature_failures(field):
    root, second = key(), key()
    value = json.loads(event(root, second, root=root))
    value[field] = "00" * 64
    raw = api.canonical(value)
    with pytest.raises(api.KeyLifecycleRejected, match="SIGNATURE_INVALID"):
        api.inspect_key_lifecycle(**arguments((raw,), root))


def test_role_signatures_are_not_interchangeable():
    root, second = key(), key()
    value = json.loads(event(root, second, root=root))
    body = bytes.fromhex(value["document_hex"])
    value["successor_signature_hex"] = second.sign(api.signing_message(body, "CURRENT")).hex()
    raw = api.canonical(value)
    with pytest.raises(api.KeyLifecycleRejected, match="SUCCESSOR_SIGNATURE_INVALID"):
        api.inspect_key_lifecycle(**arguments((raw,), root))


def test_retired_key_cannot_return_and_revocation_has_no_recovery_shortcut():
    root, second = key(), key()
    first = event(root, second, root=root)
    back = event(second, root, root=root, sequence=2, predecessor=api.sha(first))
    with pytest.raises(api.KeyLifecycleRejected, match="REACTIVATION"):
        api.inspect_key_lifecycle(**arguments((first, back), root))
    terminal = event(root, None, root=root)
    after = event(root, second, root=root, sequence=2, predecessor=api.sha(terminal))
    with pytest.raises(api.KeyLifecycleRejected, match="TERMINAL_REVOCATION"):
        api.inspect_key_lifecycle(**arguments((terminal, after), root))


@pytest.mark.parametrize(
    "mode",
    ["space", "duplicate", "nonfinite", "mutable", "pin"],
    ids=["space", "duplicate", "nonfinite", "mutable", "pin"],
)
def test_strict_records(mode):
    root = key()
    raw = event(root, key(), root=root)
    if mode == "space":
        raw += b" "
    elif mode == "duplicate":
        raw = raw.replace(b"{", b'{"signature_hex":"bad",', 1)
    elif mode == "nonfinite":
        raw = raw.replace(b"{", b'{"extra":NaN,', 1)
    elif mode == "mutable":
        args = arguments((raw,), root)
        args["records"] = (bytearray(raw),)
        with pytest.raises(api.KeyLifecycleRejected):
            api.inspect_key_lifecycle(**args)
        return
    args = arguments((raw,), root)
    if mode == "pin":
        args["expected_record_sha256s"] = ("0" * 64,)
    with pytest.raises(api.KeyLifecycleRejected):
        api.inspect_key_lifecycle(**args)


def test_actual_event_count_bound_without_limit_substitution():
    root = key()
    raw = event(root, key(), root=root)
    with pytest.raises(api.KeyLifecycleRejected, match="EXACT_INPUTS_REQUIRED"):
        api.inspect_key_lifecycle(**arguments((raw,) * 65, root))
    with pytest.raises(api.KeyLifecycleRejected, match="RECORD_BOUND"):
        api.inspect_key_lifecycle(**arguments((b"x" * (api.MAX_RECORD_BYTES + 1),), root))


def test_supplied_prefix_is_not_globally_latest_or_complete():
    root, second = key(), key()
    first = event(root, second, root=root)
    later = event(second, None, root=root, sequence=2, predecessor=api.sha(first))
    prefix = api.inspect_key_lifecycle(**arguments((first,), root))
    complete = api.inspect_key_lifecycle(**arguments((first, later), root))
    assert prefix.active_public_key_hex is not None
    assert complete.active_public_key_hex is None
    assert not prefix.global_history_completeness_verified
    assert not prefix.key_currentness_verified


def test_actual_aggregate_bound_precedes_any_partial_signature_result():
    root = key()
    records = (b"x" * api.MAX_RECORD_BYTES,) * 43
    with pytest.raises(api.KeyLifecycleRejected, match="AGGREGATE_BOUND"):
        api.inspect_key_lifecycle(**arguments(records, root))


@pytest.mark.parametrize(
    "changes",
    [dict(sequence=True), dict(action="RESTORE"), dict(subject_key_sha256="0" * 64)],
    ids=["boolean", "unsupported", "wrong-subject"],
)
def test_invalid_later_signed_events_reject_whole_supplied_chain(changes):
    root, second = key(), key()
    first = event(root, second, root=root)
    later = (
        event(second, key(), root=root, sequence=2, predecessor=api.sha(first), **changes)
        if ("sequence" not in changes)
        else event(second, key(), root=root, predecessor=api.sha(first), **changes)
    )
    with pytest.raises(api.KeyLifecycleRejected):
        api.inspect_key_lifecycle(**arguments((first, later), root))
