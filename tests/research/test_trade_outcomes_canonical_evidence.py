import json
from datetime import date, datetime

import duckdb

from nse_quant.core.regime_registry import REGIMES
from nse_quant.research.trade_outcomes import load_trade_outcomes

CANONICAL = next(iter(REGIMES))


def _connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE decisions (
            payload JSON,
            run_id VARCHAR,
            ts TIMESTAMP,
            underlying VARCHAR,
            decision_type VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE strategy_positions (
            strategy_position_id VARCHAR,
            proposal_id VARCHAR,
            opened_at TIMESTAMP,
            closed_at TIMESTAMP,
            status VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE post_trade_reviews (
            strategy_position_id VARCHAR,
            realized_pnl DOUBLE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE decision_evidence (
            evidence_id VARCHAR,
            run_id VARCHAR,
            ts TIMESTAMP,
            symbol VARCHAR,
            plugin VARCHAR,
            payload_json JSON
        )
        """
    )
    return conn


def _insert_trade(
    conn: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    proposal_id: str,
    decision_ts: datetime,
) -> None:
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
        [
            json.dumps(
                {
                    "proposal": {"proposal_id": proposal_id, "strategy": "test_strategy"},
                    "decision_audit": {
                        "regime": {
                            "as_of": (decision_ts.replace(minute=decision_ts.minute - 1)).isoformat()
                        }
                    },
                }
            ),
            run_id,
            decision_ts,
            "NIFTY",
            "paper_filled",
        ],
    )
    conn.execute(
        "INSERT INTO strategy_positions VALUES (?, ?, ?, ?, ?)",
        [
            f"position-{proposal_id}",
            proposal_id,
            datetime(2026, 1, 10, 12, 0),
            datetime(2026, 1, 12, 12, 0),
            "CLOSED",
        ],
    )
    conn.execute(
        "INSERT INTO post_trade_reviews VALUES (?, ?)",
        [f"position-{proposal_id}", 125.0],
    )


def test_trade_outcomes_use_pinned_decision_time_institutional_regime() -> None:
    conn = _connection()
    decision_ts = datetime(2026, 1, 10, 12, 0)
    _insert_trade(conn, run_id="run-1", proposal_id="p-1", decision_ts=decision_ts)
    conn.execute(
        "INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?)",
        [
            "evidence-1",
            "run-1",
            datetime(2026, 1, 10, 11, 59),
            "NIFTY",
            "institutional_regime",
            json.dumps({"regime_label": CANONICAL, "complete": True}),
        ],
    )

    outcomes = load_trade_outcomes(
        conn,
        symbol="NIFTY",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert len(outcomes) == 1
    assert outcomes[0].regime == CANONICAL
    assert outcomes[0].regime_evidence_id == "evidence-1"
    assert outcomes[0].regime_evidence_status == "CANONICAL_DECISION_TIME_EVIDENCE"
    assert outcomes[0].regime_evidence_as_of == datetime(2026, 1, 10, 11, 59)
    conn.close()


def test_missing_or_future_regime_evidence_is_explicit_not_daily_fallback() -> None:
    conn = _connection()
    decision_ts = datetime(2026, 1, 10, 12, 0)
    _insert_trade(conn, run_id="run-2", proposal_id="p-2", decision_ts=decision_ts)
    conn.execute(
        "INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?, ?)",
        [
            "future-evidence",
            "run-2",
            datetime(2026, 1, 10, 12, 1),
            "NIFTY",
            "institutional_regime",
            json.dumps({"regime_label": CANONICAL, "complete": True}),
        ],
    )
    conn.execute(
        """
        CREATE TABLE market_regimes (
            symbol VARCHAR,
            ts TIMESTAMP,
            regime VARCHAR,
            regime_vocabulary VARCHAR
        )
        """
    )
    conn.execute(
        "INSERT INTO market_regimes VALUES (?, ?, ?, ?)",
        ["NIFTY", datetime(2026, 1, 10, 11, 0), "BULL|NORMAL", "legacy_daily_v0"],
    )

    outcomes = load_trade_outcomes(
        conn,
        symbol="NIFTY",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert len(outcomes) == 1
    assert outcomes[0].regime == "UNKNOWN"
    assert outcomes[0].regime_evidence_id is None
    assert outcomes[0].regime_evidence_status == "MISSING_OR_NONCANONICAL_DECISION_TIME_EVIDENCE"
    conn.close()
