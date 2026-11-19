"""Create deterministic manifests for vectorbt backtest runs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_manifest(
    *,
    strategy: str,
    underlying: str,
    input_hash: str,
    parameters: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build a content-addressed vectorbt backtest manifest."""
    manifest = {
        "version": "vectorbt_backtest_manifest@1",
        "strategy": strategy,
        "underlying": underlying,
        "input_sha256": input_hash,
        "parameters": parameters,
        "result": result,
        "decision_eligibility_asserted": False,
    }

    return {
        **manifest,
        "manifest_sha256": hashlib.sha256(canonical_bytes(manifest)).hexdigest(),
    }
