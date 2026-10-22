"""Summarize the latest NSE Quant paper-loop cycle."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from nse_quant.core.settings import get_settings
from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show the latest paper-loop status",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional settings YAML path",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Underlying symbol; defaults to configured NIFTY",
    )
    return parser.parse_args()


def load_json(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def latest_decision(
    store: DuckDBStore,
    decision_type: str,
) -> tuple | None:
    rows = store.conn.execute(
        """
        SELECT ts, run_id, decision_type, strategy, payload
        FROM decisions
        WHERE decision_type = ?
        ORDER BY ts DESC
        LIMIT 1
        """,
        [decision_type],
    ).fetchall()

    return rows[0] if rows else None


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    args = parse_args()
    settings = get_settings(args.config)

    symbol = args.symbol or settings.market_data.default_symbol
    store = DuckDBStore(read_only=True)

    now = datetime.now(UTC)

    print_header("Platform")
    print(f"Symbol: {symbol}")
    print(f"Dry run: {settings.safety.dry_run}")
    print(f"Trading enabled: {settings.safety.trading_enabled}")
    print(f"Paper trading: {settings.safety.paper_trading}")
    print(
        "Minimum IV rank:",
        settings.analytics.min_iv_rank,
    )
    print(
        "Regime policy enforced:",
        settings.research.enforce_regime_policy,
    )

    print_header("Latest feature")
    feature_row = store.conn.execute(
        """
        SELECT ts, close, atr_1m_14, trend_15m, trend_60m
        FROM spot_features
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT 1
        """,
        [symbol],
    ).fetchone()

    if feature_row:
        ts, close, atr, trend_15m, trend_60m = feature_row
        age = (now - ts.tz_convert(UTC)).total_seconds()

        print(f"Feature time: {ts}")
        print(f"Age: {age:.0f} seconds")
        print(f"Close: {close}")
        print(f"ATR(14): {atr}")
        print(f"Trend 15m: {trend_15m}")
        print(f"Trend 60m: {trend_60m}")
    else:
        print("No spot features found.")

    print_header("Latest regime")
    regime_row = store.conn.execute(
        """
        SELECT ts, regime, trend_regime, volatility_regime, iv_regime
        FROM market_regimes
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT 1
        """,
        [symbol],
    ).fetchone()

    if regime_row:
        print(f"Regime date: {regime_row[0]}")
        print(f"Regime: {regime_row[1]}")
        print(f"Trend: {regime_row[2]}")
        print(f"Volatility: {regime_row[3]}")
        print(f"IV regime: {regime_row[4]}")
    else:
        print("No market regime found.")

    print_header("Latest signal gates")
    signal = latest_decision(store, "signal")

    if signal:
        _, run_id, _, strategy, payload = signal
        data = load_json(payload)

        print(f"Run ID: {run_id}")
        print(f"Strategy: {strategy}")
        print(f"Signal time: {signal[0]}")

        for gate in data.get("gates", []):
            status = "PASS" if gate.get("passed") else "FAIL"
            print(
                f"{status} {gate.get('gate')}: "
                f"{gate.get('reason')}"
            )

        proposal = data.get("proposal")
        if proposal:
            print(
                "Proposal ID:",
                proposal.get("proposal_id"),
            )
            print(
                "Net credit:",
                proposal.get("metadata", {}).get("net_credit"),
            )

        expected = (
            data.get("proposal", {}).get("metadata", {})
        )
        print(f"Expected move: {expected.get('expected_move_points')}")
    else:
        print("No signal decision found.")

    print_header("Expected-move diagnostics")
    diagnostics_row = store.conn.execute(
        """
        SELECT ts, payload
        FROM decisions
        WHERE decision_type = 'signal'
        ORDER BY ts DESC
        LIMIT 1
        """,
    ).fetchone()

    if diagnostics_row:
        data = load_json(diagnostics_row[1])
        gates = data.get("gates", [])

        diagnostics = next(
            (
                gate.get("details", {}).get("diagnostics", {})
                for gate in gates
                if gate.get("gate") == "expected_move_available"
            ),
            {},
        )

        if diagnostics:
            for key, value in diagnostics.items():
                print(f"{key}: {value}")
        else:
            print(
                "No expected-move diagnostics found; "
                "run a loop cycle after adding the diagnostic patch."
            )
    else:
        print("No signal decision found.")

    print_header("Latest proposal outcome")
    for decision_type in [
        "paper_filled",
        "dry_run",
        "no_proposal",
        "risk_rejected",
        "regime_policy_rejected",
        "strategy_eligibility_rejected",
        "loop_error",
    ]:
        row = latest_decision(store, decision_type)

        if row:
            payload = load_json(row[4])
            proposal_id = payload.get("proposal_id")
            exit_reason = payload.get("exit_reason")

            print(f"{decision_type}: {row[0]}")
            if proposal_id:
                print(f"  proposal_id: {proposal_id}")
            if exit_reason:
                print(f"  exit_reason: {exit_reason}")

    print_header("Paper execution counts")
    for table in ["orders", "positions", "risk_decisions", "exit_events"]:
        try:
            count = store.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(f"{table}: {count}")
        except Exception as exc:  # noqa: BLE001
            print(f"{table}: unavailable ({exc})")

    print_header("Latest exit")
    exit_row = store.conn.execute(
        """
        SELECT ts, strategy_position_id, exit_reason, details
        FROM exit_events
        ORDER BY ts DESC
        LIMIT 1
        """,
    ).fetchone()

    if exit_row:
        print(f"Exit time: {exit_row[0]}")
        print(f"Position: {exit_row[1]}")
        print(f"Exit reason: {exit_row[2]}")
        print(f"Details: {exit_row[3]}")
    else:
        print("No exit events found.")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())