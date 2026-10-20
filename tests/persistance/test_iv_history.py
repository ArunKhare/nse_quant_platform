def test_write_option_stream_computes_iv(
    test_store,
    snapshot_factory,
):
    snapshot = snapshot_factory(
        spot=23000.0,
        call_price=120.0,
        put_price=115.0,
    )

    for quote in snapshot.quotes:
        quote.iv = None

    written = test_store.write_option_stream(
        "iv-capture-test",
        snapshot,
    )

    assert written == 2

    rows = test_store.conn.execute(
        """
        SELECT iv
        FROM option_stream
        WHERE run_id = 'iv-capture-test'
        """
    ).fetchall()

    assert len(rows) == 2
    assert all(row[0] is not None for row in rows)

    assert (
        test_store.count_underlying_iv_observations(
            underlying="NIFTY"
        )
        == 1
    )