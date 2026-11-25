"""Pinned read-only S2 feature retrieval; not runner wiring or Gold publication."""

from __future__ import annotations

import json
from typing import Any

from nse_quant.analytics import s2_iv30_features as kernel
from nse_quant.data_platform import s2_series_materialization as series


def _load(
    reader: Any,
    *,
    kind: str,
    observation_id: str,
    expected_sha256: str,
    as_of: str,
    bronze: Any = None,
    vix_silver: Any = None,
) -> tuple[bytes, list[tuple[Any, ...]], dict[str, Any]]:
    raw = series.replay(
        reader,
        kind=kind,
        observation_id=observation_id,
        expected_sha256=expected_sha256,
        bronze=bronze,
        vix_silver=vix_silver,
    )
    scope = series._scope(kind, observation_id)
    rows = series._rows(reader, scope)
    if len(rows) != 1 or rows[0][1] != expected_sha256 or bytes(rows[0][4]) != raw:
        raise ValueError("S2_FEATURE_PARENT_CHANGED")
    row = rows[0]
    events = series._name(reader, "job_events", "medallion_audit")
    succeeded = reader.execute(
        f"SELECT recorded_at FROM {events} WHERE job_id=? AND state='SUCCEEDED' LIMIT 2", [row[5]]
    ).fetchall()
    if len(succeeded) != 1:
        raise ValueError("S2_FEATURE_PARENT_SUCCESS_REQUIRED")
    provenance = dict(
        observation_id=observation_id,
        materialization_sha256=expected_sha256,
        revision_id=row[0],
        materialization_available_at=max(row[6], succeeded[0][0]).isoformat(),
    )
    kernel._provenance(provenance, kernel._time(as_of))
    return raw, rows, provenance


def read_eod_feature(
    reader: Any,
    *,
    observation_id: str,
    expected_sha256: str,
    as_of: str,
    trade_date: str,
    lookback: int = 252,
    minimum_history: int = 120,
    max_age_calendar_days: int = 4,
) -> bytes:
    raw, rows, provenance = _load(
        reader, kind=series.EOD, observation_id=observation_id, expected_sha256=expected_sha256, as_of=as_of
    )
    history = kernel.canonical(json.loads(raw)["content"])
    result = kernel.build_eod_feature(
        history,
        expected_history_sha256=kernel.sha(history),
        provenance=provenance,
        as_of=as_of,
        trade_date=trade_date,
        lookback=lookback,
        minimum_history=minimum_history,
        max_age_calendar_days=max_age_calendar_days,
    )
    repeated, after, _ = _load(
        reader, kind=series.EOD, observation_id=observation_id, expected_sha256=expected_sha256, as_of=as_of
    )
    if repeated != raw or after != rows:
        raise ValueError("S2_FEATURE_PARENT_CHANGED")
    return result


def read_live_feature(
    reader: Any,
    bronze: Any,
    vix_silver: Any,
    *,
    observation_id: str,
    expected_sha256: str,
    as_of: str,
    max_age_seconds: float = 300,
) -> bytes:
    from nse_quant.data_platform import india_vix_recording as vix

    raw, rows, provenance = _load(
        reader,
        kind=series.MINUTE,
        observation_id=observation_id,
        expected_sha256=expected_sha256,
        as_of=as_of,
        bronze=bronze,
        vix_silver=vix_silver,
    )
    revisions = json.loads(raw)["content"]["revisions"]
    samples = {revision: vix.replay_vix_silver(bronze, vix_silver, revision_id=revision) for revision in revisions}
    result = kernel.build_live_feature(samples, provenance=provenance, as_of=as_of, max_age_seconds=max_age_seconds)
    repeated, after, _ = _load(
        reader,
        kind=series.MINUTE,
        observation_id=observation_id,
        expected_sha256=expected_sha256,
        as_of=as_of,
        bronze=bronze,
        vix_silver=vix_silver,
    )
    if repeated != raw or after != rows:
        raise ValueError("S2_FEATURE_PARENT_CHANGED")
    return result
