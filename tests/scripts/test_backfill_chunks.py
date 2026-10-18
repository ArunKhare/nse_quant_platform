from datetime import UTC, datetime, timedelta

from scripts.backfill_candles import chunk_bounds


def test_minute_requests_are_chunked_to_60_days() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=150)

    chunks = chunk_bounds(start, end, 60)

    assert len(chunks) == 3
    assert chunks[0][0] == start
    assert chunks[-1][1] == end


def test_partial_final_chunk_is_supported() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=70)

    chunks = chunk_bounds(start, end, 60)

    assert len(chunks) == 2
    assert (chunks[1][1] - chunks[1][0]).days == 10