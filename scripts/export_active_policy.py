"""Export the active walk-forward regime policy for operational use."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.persistence.duckdb_store import DuckDBStore

DEFAULT_OUTPUT = Path("data/active_regime_policy.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the active regime policy")

    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        help=(
            "Optional ISO datetime; defaults to current UTC time. "
            "Used to select the applicable walk-forward policy."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSON path",
    )

    return parser.parse_args()


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)

    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError("--as-of must be timezone-aware")

    return parsed.astimezone(UTC)


def build_active_policy(
    *,
    symbol: str,
    policy: dict[str, Any] | None,
    as_of: datetime,
) -> dict[str, Any]:
    if policy is None:
        return {
            "symbol": symbol,
            "selection_status": "UNAVAILABLE",
            "as_of": as_of.isoformat(),
            "allowed_regimes": [],
            "risk_limits": {},
            "actionable": False,
            "reason": "no_policy_available",
        }

    test_end = policy["test_end"]

    expires_at = test_end.isoformat() if hasattr(test_end, "isoformat") else str(test_end)

    is_ready = policy["selection_status"] == "READY"
    is_current = test_end >= as_of.date()

    return {
        "symbol": symbol,
        "policy_id": policy.get("policy_id"),
        "selection_status": policy["selection_status"],
        "as_of": as_of.isoformat(),
        "test_end": expires_at,
        "expires_at": expires_at,
        "allowed_regimes": sorted(policy["allowed_regimes"]),
        "risk_limits": policy["risk_limits"],
        "actionable": is_ready and is_current,
        "reason": (
            "active"
            if is_ready and is_current
            else "policy_expired"
            if is_ready
            else policy["selection_status"].lower()
        ),
    }


def write_json_atomically(
    payload: dict[str, Any],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    temporary_path.replace(output_path)
    return output_path


def main() -> int:
    args = parse_args()
    as_of = parse_as_of(args.as_of)

    store = DuckDBStore(read_only=True)

    try:
        policy = store.latest_regime_policy(
            symbol=args.symbol,
            as_of=as_of,
        )

        active_policy = build_active_policy(
            symbol=args.symbol,
            policy=policy,
            as_of=as_of,
        )

        output_path = Path(args.output)
        write_json_atomically(active_policy, output_path)

        print(
            f"{args.symbol}: status={active_policy['selection_status']} "
            f"actionable={active_policy['actionable']} "
            f"output={output_path}"
        )
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
