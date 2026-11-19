"""Real SQL coverage for event-risk blackout and ingestion boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from nse_quant.core.settings import EventRiskSettings
from nse_quant.research.evidence_plugins.event_risk import EventRiskPlugin

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("event_minutes", "ingested_minutes", "expected"),
    [
        (-31, -60, 0),
        (-30, -60, 1),
        (-15, -60, 1),
        (0, 0, 1),
        (30, -60, 1),
        (31, -60, 0),
        (15, 1, 0),
        (15, None, 0),
    ],
)
def test_blackout_and_ingestion_boundaries(event_minutes, ingested_minutes, expected):
    with duckdb.connect() as conn:
        conn.execute(
            """
            CREATE TABLE market_events (
                event_id VARCHAR,
                event_type VARCHAR,
                event_ts TIMESTAMPTZ,
                importance VARCHAR,
                affected_underlyings JSON,
                ingested_at TIMESTAMPTZ
            )
            """
        )
        ingested_at = None if ingested_minutes is None else AT + timedelta(minutes=ingested_minutes)
        conn.execute(
            "INSERT INTO market_events VALUES (?,?,?,?,?,?)",
            [
                "event-1",
                "RBI_POLICY",
                AT + timedelta(minutes=event_minutes),
                "high",
                '["NIFTY"]',
                ingested_at,
            ],
        )
        plugin = EventRiskPlugin(
            store=SimpleNamespace(conn=conn),
            settings=EventRiskSettings(
                enabled=True,
                block_new_entries=True,
                blackout_minutes_before=30,
                blackout_minutes_after=30,
            ),
        )

        result = plugin.build(SimpleNamespace(ts=AT, symbol="NIFTY"))

        assert result["events_considered"] == expected
        assert result["blocking_events"] == expected
        assert result["block_new_entries"] is bool(expected)
