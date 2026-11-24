import json
import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any

from nse_quant.market_data.market_snapshot_service import SnapshotUnavailable, read_snapshot


class Contract(unittest.TestCase):
    def test_snapshot_lifecycle(self):
        now = datetime.now(UTC)
        clock = now.isoformat()
        item = dict(source_time=clock, received_at=clock, capture_id="test")
        state: dict[str, Any] = dict(
            version=1,
            underlying="NIFTY",
            capture_id="test",
            captured_at=clock,
            spot=dict(item, price=100),
            quotes=[dict(item, token=1, bid=2, ask=3)],
        )
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE market_snapshot_slot(slot INTEGER PRIMARY KEY, payload TEXT)")

        def read():
            return read_snapshot(
                db, underlying="NIFTY", expected_tokens=frozenset({1}), as_of=now, max_age=timedelta(seconds=5)
            )

        with self.assertRaisesRegex(SnapshotUnavailable, "no_snapshot"):
            read()
        db.execute("INSERT INTO market_snapshot_slot VALUES (1,?)", (json.dumps(state),))
        self.assertEqual(read(), state)
        for key, value, error in [
            ("token", 2, "incomplete_chain"),
            ("capture_id", "other", "mixed_capture"),
            ("source_time", (now - timedelta(seconds=6)).isoformat(), "stale"),
        ]:
            changed = dict(state, quotes=[dict(state["quotes"][0], **{key: value})])
            db.execute("UPDATE market_snapshot_slot SET payload=?", (json.dumps(changed),))
            with self.assertRaisesRegex(SnapshotUnavailable, error):
                read()
        db.close()
        with self.assertRaisesRegex(SnapshotUnavailable, "service_unavailable"):
            read()
