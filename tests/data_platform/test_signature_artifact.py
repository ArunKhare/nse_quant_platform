"""Pure artifact parsing tests, not native provenance or issuer verification."""

import base64
import hashlib
import json

import pytest

from nse_quant.data_platform.signature_artifact import (
    MAX_BYTES,
    VERSION,
    SignatureArtifactRejected,
    parse_signature_artifact,
)


def artifact(**changes):
    value = dict(
        schema=VERSION,
        assertion_id="a" * 64,
        record_id="r1",
        payload_sha256="b" * 64,
        public_key_base64=base64.b64encode(bytes(32)).decode(),
        signature_base64=base64.b64encode(bytes(64)).decode(),
    )
    value.update(changes)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_exact_artifact_does_not_verify_signature():
    raw = artifact()
    value = parse_signature_artifact(raw)
    assert value.artifact_sha256 == hashlib.sha256(raw).hexdigest()
    assert value.public_key == bytes(32)
    assert value.signature == bytes(64)
    assert value.assertion_id == "a" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "unknown@2"},
        {"extra": True},
        {"record_id": ""},
        {"record_id": "x" * 65},
        {"record_id": True},
        {"assertion_id": "A" * 64},
        {"payload_sha256": None},
        {"public_key_base64": "!!!!"},
        {"signature_base64": ""},
        {"public_key_base64": "AA=="},
        {"signature_base64": True},
    ],
    ids=[
        "schema",
        "extra",
        "empty-id",
        "long-id",
        "bool-id",
        "uppercase-pin",
        "null-pin",
        "bad-base64",
        "empty-signature",
        "short-key",
        "bool-signature",
    ],
)
def test_strict_fields(changes):
    with pytest.raises(SignatureArtifactRejected):
        parse_signature_artifact(artifact(**changes))


@pytest.mark.parametrize(
    "mode", ["lf", "space", "bom", "duplicate", "nonfinite", "later", "bad-utf8", "array"]
)
def test_no_prefix_or_encoding_salvage(mode):
    raw = artifact()
    cases = {
        "lf": raw + b"\n",
        "space": b" " + raw,
        "bom": b"\xef\xbb\xbf" + raw,
        "duplicate": raw.replace(b'"record_id":', b'"record_id":"x","record_id":'),
        "nonfinite": raw.replace(b'"record_id":"r1"', b'"record_id":NaN'),
        "later": raw + b"{}",
        "bad-utf8": b"\xff",
        "array": b"[]",
    }
    with pytest.raises(SignatureArtifactRejected):
        parse_signature_artifact(cases[mode])


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"x" * (MAX_BYTES + 1), id="oversized"),
        pytest.param(bytearray(b"x"), id="mutable"),
    ],
)
def test_byte_bounds(raw):
    with pytest.raises(SignatureArtifactRejected, match="BYTES_LIMIT"):
        parse_signature_artifact(raw)


def test_noncanonical_base64_padding_bits_rejected():
    raw = artifact()
    value = json.loads(raw)
    value["public_key_base64"] = value["public_key_base64"][:-2] + "B="
    modified = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(SignatureArtifactRejected, match="BINARY_ENCODING"):
        parse_signature_artifact(modified)
