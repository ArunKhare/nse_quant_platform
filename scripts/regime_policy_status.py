"""Show the operational status of the active regime policy."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show active regime-policy status"
    )

    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--policy-file",
        default="data/active_regime_policy.json",
    )

    return parser.parse_args()


def load_policy(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    policy_path = Path(args.policy_file)
    policy = load_policy(policy_path)

    if policy is None:
        print(
            f"No exported policy found: {policy_path}\n"
            "Run scripts/export_active_policy.py first."
        )
        return 1

    as_of = datetime.now(UTC)
    policy_as_of = datetime.fromisoformat(policy["as_of"])
    age_seconds = (as_of - policy_as_of).total_seconds()

    print(f"Symbol: {policy['symbol']}")
    print(f"Status: {policy['selection_status']}")
    print(f"Actionable: {policy['actionable']}")
    print(f"Reason: {policy['reason']}")
    print(f"Exported at: {policy['as_of']}")
    print(f"Policy age: {age_seconds:.0f} seconds")
    print(f"Expires at: {policy.get('expires_at')}")
    print("Allowed regimes:")

    for regime in policy["allowed_regimes"]:
        limits = policy["risk_limits"].get(regime, {})
        print(
            f"  - {regime}: "
            f"lots={limits.get('max_lots_per_order')}, "
            f"open_positions={limits.get('max_open_positions')}, "
            f"notional={limits.get('max_notional_exposure')}, "
            f"vega={limits.get('max_portfolio_vega')}, "
            f"daily_loss={limits.get('max_daily_loss')}"
        )

    if not policy["allowed_regimes"]:
        print("  - none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())