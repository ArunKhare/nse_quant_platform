import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from nse_quant.market_data.quack_snapshot_boundary import SnapshotPublisher, serve


class PublisherTests(unittest.TestCase):
    def test_commit_rollback_and_monotonicity(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        publisher = SnapshotPublisher(db)
        publisher.initialize()
        now = datetime.now(UTC)
        item = dict(capture_id="one", source_time=now.isoformat(), received_at=now.isoformat())
        snapshot = dict(
            version=1,
            underlying="NIFTY",
            capture_id="one",
            captured_at=now.isoformat(),
            spot=dict(item, price=100),
            quotes=[dict(item, token=1, bid=2, ask=3)],
        )
        args = dict(underlying="NIFTY", expected_tokens=frozenset({1}), as_of=now, max_age=timedelta(seconds=10))
        publisher.publish(snapshot, **args)
        before = db.execute("SELECT payload FROM market_snapshot_slot").fetchone()
        with self.assertRaisesRegex(ValueError, "advancing"):
            publisher.publish(snapshot, **args)
        changed = dict(snapshot, captured_at=(now + timedelta(seconds=1)).isoformat(), quotes=[])
        with self.assertRaises(ValueError):
            publisher.publish(changed, **dict(args, as_of=now + timedelta(seconds=1)))
        self.assertEqual(before, db.execute("SELECT payload FROM market_snapshot_slot").fetchone())
        with (
            patch("os.getpid", return_value=publisher.pid + 1),
            self.assertRaisesRegex(RuntimeError, "process"),
        ):
            publisher.publish(snapshot, **args)
        db.close()

    def test_bad_port_does_not_start(self):
        with self.assertRaises(ValueError):
            serve(None, port=0)
