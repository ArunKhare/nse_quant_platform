"""Pure, content-pinned minute bars from replayed native VIX Silver revisions.

No interpolation, gap fill, EOD inference, Gold publication or decision authority.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import india_vix_recording as vix
from nse_quant.data_platform import legacy_silver_common as base

VERSION = "s2-vix-replayed-minute-bars@1"
MAX_REVISIONS = 4096


def build_minute_bars(bronze: Any, silver: Any, *, revision_ids: list[str]) -> bytes:
    if (
        type(revision_ids) is not list
        or not 1 <= len(revision_ids) <= MAX_REVISIONS
        or len(set(revision_ids)) != len(revision_ids)
        or any(not base.pin(pin) for pin in revision_ids)
    ):
        raise ValueError("EXACT_UNIQUE_VIX_REVISION_SET_REQUIRED")
    groups: dict[str, list[tuple[datetime, str, float]]] = {}
    tokens = set()
    for revision in sorted(revision_ids):
        record = vix.replay_vix_silver(bronze, silver, revision_id=revision)
        if record["quality_state"] != "valid_observation":
            raise ValueError("VIX_REJECTED_REVISION_NOT_A_BAR_INPUT")
        observation = record["observation"]
        if observation["iv30_source"] != "india_vix" or observation["decision_eligibility_asserted"] is not False:
            raise ValueError("VIX_SOURCE_OR_AUTHORITY_MISMATCH")
        stamp = datetime.fromisoformat(observation["source_time"])
        if stamp.utcoffset() is None:
            raise ValueError("AWARE_VIX_SOURCE_CLOCK_REQUIRED")
        stamp = stamp.astimezone(UTC)
        bucket = stamp.replace(second=0, microsecond=0).isoformat()
        tokens.add(observation["instrument_token"])
        groups.setdefault(bucket, []).append((stamp, revision, observation["iv30"]))
    if len(tokens) != 1:
        raise ValueError("VIX_INSTRUMENT_CHANGED_WITHIN_SERIES")
    rows = []
    for minute, samples in sorted(groups.items()):
        samples.sort()
        if len({stamp for stamp, _, _ in samples}) != len(samples):
            raise ValueError("AMBIGUOUS_VIX_SOURCE_TIMESTAMP")
        values = [value for _, _, value in samples]
        rows.append(
            dict(
                minute=minute,
                open=values[0],
                high=max(values),
                low=min(values),
                close=values[-1],
                sample_count=len(values),
                source_revisions=[revision for _, revision, _ in samples],
            )
        )
    return vix.canonical(
        dict(
            version=VERSION,
            revisions=sorted(revision_ids),
            bars=rows,
            iv30_source="india_vix",
            units="decimal",
            gaps_filled=False,
            daily_close_asserted=False,
            decision_eligibility_asserted=False,
        )
    )


def replay_minute_bars(bronze: Any, silver: Any, raw: bytes, *, expected_sha256: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= 2 * 1024 * 1024 or base.sha(raw) != expected_sha256:
        raise ValueError("VIX_BAR_PIN_OR_BYTE_BOUND")
    doc = json.loads(raw)
    if build_minute_bars(bronze, silver, revision_ids=doc["revisions"]) != raw:
        raise ValueError("VIX_BAR_REPLAY_MISMATCH")
    return doc
