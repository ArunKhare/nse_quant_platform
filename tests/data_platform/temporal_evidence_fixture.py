"""Disposable signed time claims; no independent authority or source time proof."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform import signed_temporal_evidence as api

T = datetime(2026, 1, 1, tzinfo=UTC)
SUPPORT = b"synthetic retained time claim, not authenticated external proof"


def key():
    return Ed25519PrivateKey.generate()


def public(private):
    return private.public_key().public_bytes_raw()


def subject():
    return api.TemporalSubject("TEST_NS", "INDEX", "a" * 64, "b" * 64, "c" * 64)


def declaration(
    private, *, target=None, sequence=1, predecessor=None, lifecycle_tip="d" * 64, **changes
):
    value = dict(
        schema=api.VERSION,
        series_id="SYNTHETIC_TIME_CLAIMS",
        subject=asdict(subject() if target is None else target),
        sequence=sequence,
        predecessor_sha256=predecessor,
        lifecycle_tip_sha256=lifecycle_tip,
        statement_kind="ASSERT",
        declared_available_at=api.clock(T),
        declared_economic_from=api.clock(T),
        declared_economic_until=api.clock(T + timedelta(hours=1)),
        support_sha256s=[api.sha(SUPPORT)],
    )
    value.update(changes)
    raw = api.canonical(value)
    return api.encode_signed_declaration(raw, private.sign(api.signing_message(raw)))


def arguments(records, keys, *, target=None, request=None):
    return dict(
        records=tuple(records),
        expected_record_sha256s=tuple(api.sha(x) for x in records),
        expected_tip_sha256=api.sha(records[-1]),
        verification_keys=tuple(public(k) for k in keys),
        support_blobs=(SUPPORT,),
        subject=subject() if target is None else target,
        request=api.TemporalRequest(T, T) if request is None else request,
    )


def lifecycle_event(current, successor, root, *, sequence=1, predecessor=None):
    from nse_quant.data_platform import observed_key_lifecycle as lifecycle

    scope = lifecycle.LifecycleScope("SYNTHETIC", "TEST_NS", "INDEX", "TEST_POLICY")
    raw = lifecycle.canonical(
        dict(
            schema=lifecycle.EVENT_VERSION,
            scope=asdict(scope),
            root_key_sha256=api.sha(public(root)),
            sequence=sequence,
            predecessor_sha256=predecessor,
            action="REVOKE" if successor is None else "ROTATE",
            subject_key_sha256=api.sha(public(current)),
            successor_public_key_hex=None if successor is None else public(successor).hex(),
        )
    )
    return lifecycle.encode_signed_event(
        raw,
        current.sign(lifecycle.signing_message(raw, "CURRENT")),
        None if successor is None else successor.sign(lifecycle.signing_message(raw, "SUCCESSOR")),
    ), scope
