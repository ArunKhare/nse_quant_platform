"""Export the active walk-forward regime policy for operational use."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from nse_quant.core.regime_registry import REGIME_REGISTRY_VERSION, is_canonical_regime_label
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
    base = {
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "regime_registry_version": REGIME_REGISTRY_VERSION,
    }
    if policy is None:
        return {
            **base,
            "regime_vocabulary": None,
            "selection_status": "UNAVAILABLE",
            "allowed_regimes": [],
            "risk_limits": {},
            "actionable": False,
            "reason": "no_policy_available",
        }

    allowed = policy.get("allowed_regimes")
    risk_limits = policy.get("risk_limits")
    vocabulary = policy.get("regime_vocabulary")
    test_end = policy.get("test_end")

    allowed_values = (
        list(allowed)
        if isinstance(allowed, (list, tuple, set, frozenset))
        else []
    )
    allowed_labels = [label for label in allowed_values if isinstance(label, str)]
    labels_valid = (
        bool(allowed_labels)
        and len(allowed_labels) == len(allowed_values)
        and all(is_canonical_regime_label(label) for label in allowed_labels)
    )
    if isinstance(test_end, datetime):
        test_end_date: date | None = test_end.date()
        expires_at: str | None = test_end.isoformat()
    elif isinstance(test_end, date):
        test_end_date = test_end
        expires_at = test_end.isoformat()
    else:
        test_end_date = None
        expires_at = None
    expiry_valid = test_end_date is not None
    limits_valid = (
        labels_valid
        and isinstance(risk_limits, dict)
        and all(is_canonical_regime_label(label) for label in risk_limits)
        and set(risk_limits).issubset(set(allowed_labels))
        and all(isinstance(value, dict) for value in risk_limits.values())
    )
    policy_valid = vocabulary == "canonical_v1" and labels_valid and limits_valid and expiry_valid

    if not policy_valid:
        return {
            **base,
            "regime_vocabulary": vocabulary,
            "policy_id": policy.get("policy_id"),
            "selection_status": "INVALID_POLICY",
            "allowed_regimes": [],
            "risk_limits": {},
            "actionable": False,
            "reason": "canonical_policy_validation_failed",
        }

    # policy_valid guarantees both values are populated and date-compatible.
    assert test_end_date is not None
    assert expires_at is not None
    is_current = test_end_date >= as_of.date()

    is_ready = policy.get("selection_status") == "READY"
    actionable = is_ready and is_current
    return {
        **base,
        "regime_vocabulary": "canonical_v1",
        "policy_id": policy.get("policy_id"),
        "selection_status": policy.get("selection_status", "UNAVAILABLE"),
        "test_end": expires_at,
        "expires_at": expires_at,
        "allowed_regimes": sorted(allowed_labels),
        "risk_limits": risk_limits,
        "actionable": actionable,
        "reason": (
            "active"
            if actionable
            else "policy_expired"
            if is_ready and not is_current
            else str(policy.get("selection_status", "unavailable")).lower()
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
