from scripts.migration.check_option_stream_bronze_completeness import (
    json_sha256,
    sha256_bytes,
)


def test_hash_helpers_are_deterministic():
    payload = b'{"ok":true}'
    assert sha256_bytes(payload) == sha256_bytes(payload)
    assert json_sha256({"a": 1}) == json_sha256({"a": 1})
