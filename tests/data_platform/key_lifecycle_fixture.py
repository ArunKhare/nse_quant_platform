"""Disposable real Ed25519 fixtures; no real authority/registration/acquisition."""

from dataclasses import asdict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.observed_key_lifecycle import (
    EVENT_VERSION,
    LifecycleScope,
    canonical,
    encode_signed_event,
    sha,
    signing_message,
)


def key():
    return Ed25519PrivateKey.generate()


def public(private):
    return private.public_key().public_bytes_raw()


def scope():
    return LifecycleScope("SYNTHETIC", "TEST_NS", "INDEX", "TEST_POLICY")


def event(current, successor, *, root, sequence=1, predecessor=None, target=None, **changes):
    value = dict(
        schema=EVENT_VERSION,
        scope=asdict(scope() if target is None else target),
        root_key_sha256=sha(public(root)),
        sequence=sequence,
        predecessor_sha256=predecessor,
        action="REVOKE" if successor is None else "ROTATE",
        subject_key_sha256=sha(public(current)),
        successor_public_key_hex=None if successor is None else public(successor).hex(),
    )
    value.update(changes)
    raw = canonical(value)
    return encode_signed_event(
        raw,
        current.sign(signing_message(raw, "CURRENT")),
        None if successor is None else successor.sign(signing_message(raw, "SUCCESSOR")),
    )


def arguments(records, root):
    return dict(
        records=tuple(records),
        expected_record_sha256s=tuple(sha(x) for x in records),
        root_public_key=public(root),
        expected_root_key_sha256=sha(public(root)),
        scope=scope(),
    )
