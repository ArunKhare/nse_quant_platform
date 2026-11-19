def test_revision_identity_is_deterministic():
    from scripts.migration.build_option_stream_silver import revision_id_for

    a = revision_id_for(
        snapshot_id="a" * 64,
        capture_event_id="b" * 64,
        envelope_hash="c" * 64,
        recording_fingerprint="d" * 64,
    )
    b = revision_id_for(
        snapshot_id="a" * 64,
        capture_event_id="b" * 64,
        envelope_hash="c" * 64,
        recording_fingerprint="d" * 64,
    )
    assert a == b
