"""Export point-in-time NIFTY features for diagnostic regime calibration.

The exporter reads completed daily and 1-minute NIFTY candles plus the legacy
option stream from DuckDB. India VIX is supplied as an external NSE CSV.
It writes only complete, same-session observations; it never fills missing
inputs, extrapolates the volatility term structure, or promotes thresholds.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.institutional_regime_price_action_v5 import (
    DailyBar,
    _adx_series,
    _metrics_at,
)

IST = ZoneInfo("Asia/Kolkata")
EXPORT_VERSION = "institutional_regime_calibration_export_v1"
FEATURE_CONTRACT = "institutional_regime_calibration_csv_v1"
MINIMUM_CALIBRATION_SESSIONS = 423
CSV_COLUMNS = [
    "session",
    "ivp",
    "iv30_minus_iv90",
    "rr25",
    "adx14",
    "plus_di14",
    "minus_di14",
    "er20",
    "chop14",
    "atr14",
    "atr_percentile",
    "bandwidth_percentile",
    "range_position",
    "change20",
    "sma20_slope",
    "realized_variance",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export point-in-time NIFTY institutional regime calibration features."
    )
    parser.add_argument("--india-vix-csv", required=True, type=Path)
    parser.add_argument("--db-path", type=Path, default=Path("data/nse_quant.duckdb"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research/nifty_regime_calibration.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/research/nifty_regime_sources.json"),
    )
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--min-intraday-observations", type=int, default=300)
    parser.add_argument("--iv-lookback-sessions", type=int, default=252)
    parser.add_argument("--iv-min-observations", type=int, default=30)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_vix_date(value: str) -> date:
    text = value.strip()
    for pattern in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported_india_vix_date:{value!r}")


def _percentile_rank(values: list[float], current: float) -> float:
    if not values:
        raise ValueError("percentile_requires_observations")
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return 100.0 * (less + 0.5 * equal) / len(values)


def _load_india_vix(
    path: Path,
    *,
    lookback_sessions: int,
    minimum_observations: int,
    end_date: date,
) -> tuple[dict[date, float], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if lookback_sessions < 2 or minimum_observations < 2 or minimum_observations > lookback_sessions:
        raise ValueError("invalid_india_vix_percentile_window")

    parsed: dict[date, float] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if reader.fieldnames is None:
            raise ValueError("india_vix_csv_missing_header")
        headers = {str(name).strip().casefold(): name for name in reader.fieldnames}
        date_column = headers.get("date")
        close_column = headers.get("close")
        if date_column is None or close_column is None:
            raise ValueError("india_vix_csv_requires_date_and_close_columns")
        for line_number, row in enumerate(reader, start=2):
            session = _parse_vix_date(str(row.get(date_column, "")))
            raw_close = str(row.get(close_column, "")).replace(",", "").strip()
            try:
                close = float(raw_close)
            except ValueError as exc:
                raise ValueError(f"invalid_india_vix_close_at_line:{line_number}") from exc
            if not math.isfinite(close) or close <= 0:
                raise ValueError(f"invalid_india_vix_close_at_line:{line_number}")
            if session in parsed:
                raise ValueError(f"duplicate_india_vix_session:{session.isoformat()}")
            if session <= end_date:
                parsed[session] = close

    ordered = sorted(parsed.items())
    ivp: dict[date, float] = {}
    closes: list[float] = []
    for session, close in ordered:
        closes.append(close)
        window = closes[-lookback_sessions:]
        if len(window) >= minimum_observations:
            # The current close is included; no future session enters this rank.
            ivp[session] = _percentile_rank(window, close)

    summary = {
        "path": str(path),
        "sha256": _sha256(path),
        "rows_through_end_date": len(ordered),
        "first_session": ordered[0][0].isoformat() if ordered else None,
        "last_session": ordered[-1][0].isoformat() if ordered else None,
        "ivp_observations": len(ivp),
        "ivp_definition": (
            "India VIX Close percentile rank over the trailing "
            f"{lookback_sessions} available sessions including current; "
            f"minimum {minimum_observations} observations; no future data"
        ),
        "close_units": "India VIX index points",
    }
    return ivp, summary


def _table_exists(conn: Any, table_name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        ).fetchone()[0]
    )


def _load_daily_bars(
    conn: Any,
    *,
    end_date: date,
) -> tuple[list[DailyBar], dict[str, Any]]:
    if not _table_exists(conn, "spot_candles"):
        return [], {"table": "spot_candles", "available": False, "rows": 0}
    rows = conn.execute(
        """
        SELECT
            CAST(timezone('Asia/Kolkata', ts) AS DATE) AS session,
            ts, open, high, low, close, volume
        FROM spot_candles
        WHERE symbol = 'NIFTY'
          AND interval = 'day'
          AND CAST(timezone('Asia/Kolkata', ts) AS DATE) <= ?
        ORDER BY ts
        """,
        [end_date],
    ).fetchall()

    latest_by_session: dict[date, tuple[Any, ...]] = {}
    for row in rows:
        latest_by_session[row[0]] = row

    bars: list[DailyBar] = []
    for session in sorted(latest_by_session):
        _session, _ts, opening, high, low, close, volume = latest_by_session[session]
        values = (opening, high, low, close)
        if any(value is None or not math.isfinite(float(value)) for value in values):
            continue
        if min(float(value) for value in values) <= 0:
            continue
        if float(high) < max(float(opening), float(close), float(low)):
            continue
        if float(low) > min(float(opening), float(close), float(high)):
            continue
        bars.append(
            DailyBar(
                trade_date=session,
                open=float(opening),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume or 0.0),
            )
        )

    summary = {
        "table": "spot_candles",
        "interval": "day",
        "available": True,
        "rows_read": len(rows),
        "valid_sessions": len(bars),
        "first_session": bars[0].trade_date.isoformat() if bars else None,
        "last_session": bars[-1].trade_date.isoformat() if bars else None,
    }
    return bars, summary


def _price_features(bars: list[DailyBar]) -> dict[date, dict[str, float]]:
    if not bars:
        return {}
    atr, plus_di, minus_di, adx = _adx_series(bars)
    result: dict[date, dict[str, float]] = {}
    for index, bar in enumerate(bars):
        metrics = _metrics_at(bars, index, atr, plus_di, minus_di, adx)
        if metrics is None:
            continue
        result[bar.trade_date] = {
            "adx14": metrics.adx,
            "plus_di14": metrics.plus_di,
            "minus_di14": metrics.minus_di,
            "er20": metrics.er20,
            "chop14": metrics.chop14,
            "atr14": metrics.atr14,
            "atr_percentile": metrics.atr_percentile,
            "bandwidth_percentile": metrics.bandwidth_percentile,
            "range_position": metrics.range_position,
            "change20": metrics.change20,
            "sma20_slope": metrics.sma20_slope,
        }
    return result


def _intraday_session_coverage(
    counts: dict[date, int],
    *,
    minimum_observations: int,
) -> list[dict[str, Any]]:
    """Return auditable per-session observation counts and eligibility reasons."""
    return [
        {
            "session": session.isoformat(),
            "observations": observations,
            "minimum_observations": minimum_observations,
            "eligible": observations >= minimum_observations,
            "rejection_reason": None if observations >= minimum_observations else "below_minimum_observations",
        }
        for session, observations in sorted(counts.items())
    ]


def _load_realized_variance(
    conn: Any,
    *,
    end_date: date,
    minimum_observations: int,
) -> tuple[dict[date, float], dict[str, Any]]:
    if not _table_exists(conn, "spot_candles"):
        return {}, {
            "table": "spot_candles",
            "interval": "1m",
            "available": False,
            "sessions": 0,
        }
    rows = conn.execute(
        """
        SELECT
            CAST(timezone('Asia/Kolkata', ts) AS DATE) AS session,
            ts, close
        FROM spot_candles
        WHERE symbol = 'NIFTY'
          AND interval = '1m'
          AND CAST(timezone('Asia/Kolkata', ts) AS DATE) <= ?
          AND close IS NOT NULL
          AND isfinite(close)
          AND close > 0
        ORDER BY ts
        """,
        [end_date],
    ).fetchall()

    closes_by_session: dict[date, list[float]] = defaultdict(list)
    for session, _ts, close in rows:
        closes_by_session[session].append(float(close))

    realized_variance: dict[date, float] = {}
    counts = {session: len(closes) for session, closes in closes_by_session.items()}
    for session, closes in closes_by_session.items():
        if len(closes) < minimum_observations:
            continue
        value = sum(math.log(current / previous) ** 2 for previous, current in zip(closes, closes[1:], strict=False))
        if math.isfinite(value) and value >= 0:
            realized_variance[session] = value

    summary = {
        "table": "spot_candles",
        "interval": "1m",
        "available": True,
        "rows_read": len(rows),
        "sessions_with_intraday_bars": len(closes_by_session),
        "sessions_meeting_minimum": len(realized_variance),
        "minimum_observations_per_session": minimum_observations,
        "observation_count_min": min(counts.values()) if counts else None,
        "observation_count_median": sorted(counts.values())[len(counts) // 2] if counts else None,
        "observation_count_max": max(counts.values()) if counts else None,
        "session_coverage": _intraday_session_coverage(
            counts,
            minimum_observations=minimum_observations,
        ),
        "definition": "sum of squared consecutive within-session 1-minute log returns; not annualized",
    }
    return realized_variance, summary


def _normalise_option_type(value: Any) -> str | None:
    text = str(value).strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CALL"
    if text in {"PE", "PUT", "P"}:
        return "PUT"
    return None


def _interpolate_total_variance(
    points: list[tuple[int, float]],
    target_days: int,
) -> float | None:
    """Interpolate IV in total-variance space; never extrapolate."""
    ordered = sorted((days, iv) for days, iv in points if days > 0 and math.isfinite(iv) and iv > 0)
    if not ordered:
        return None
    exact = [iv for days, iv in ordered if days == target_days]
    if exact:
        return exact[-1]
    lower = [(days, iv) for days, iv in ordered if days < target_days]
    upper = [(days, iv) for days, iv in ordered if days > target_days]
    if not lower or not upper:
        return None
    lower_days, lower_iv = lower[-1]
    upper_days, upper_iv = upper[0]
    weight = (target_days - lower_days) / (upper_days - lower_days)
    lower_variance = lower_iv * lower_iv * lower_days / 365.0
    upper_variance = upper_iv * upper_iv * upper_days / 365.0
    target_variance = lower_variance + weight * (upper_variance - lower_variance)
    target_time = target_days / 365.0
    if target_variance <= 0 or target_time <= 0:
        return None
    return math.sqrt(target_variance / target_time)


def _option_surface_points(
    rows: list[tuple[Any, ...]],
    *,
    session: date,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]], list[tuple[int, float]]]:
    """Extract valid ATM and 25-delta IV observations under the surface contract."""
    by_expiry: dict[date, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: {"CALL": [], "PUT": []}
    )
    for expiry, option_type, iv, delta in rows:
        kind = _normalise_option_type(option_type)
        if kind is None or expiry is None or iv is None or delta is None:
            continue
        expiry_date = expiry.date() if isinstance(expiry, datetime) else expiry
        days = (expiry_date - session).days
        iv_value = float(iv)
        delta_value = float(delta)
        if days <= 0 or not math.isfinite(iv_value) or not 0.001 <= iv_value <= 5.0:
            continue
        if not math.isfinite(delta_value) or not -1.0 <= delta_value <= 1.0:
            continue
        by_expiry[expiry_date][kind].append((iv_value, delta_value))

    atm_points: list[tuple[int, float]] = []
    call25_points: list[tuple[int, float]] = []
    put25_points: list[tuple[int, float]] = []
    for expiry, sides in by_expiry.items():
        days = (expiry - session).days
        calls = sides["CALL"]
        puts = sides["PUT"]
        if calls and puts:
            call_atm = min(calls, key=lambda item: abs(item[1] - 0.50))
            put_atm = min(puts, key=lambda item: abs(item[1] + 0.50))
            if abs(call_atm[1] - 0.50) <= 0.10 and abs(put_atm[1] + 0.50) <= 0.10:
                atm_points.append((days, (call_atm[0] + put_atm[0]) / 2.0))
        call_wing = [item for item in calls if item[1] > 0]
        put_wing = [item for item in puts if item[1] < 0]
        if call_wing and put_wing:
            call25 = min(call_wing, key=lambda item: abs(item[1] - 0.25))
            put25 = min(put_wing, key=lambda item: abs(item[1] + 0.25))
            if abs(call25[1] - 0.25) <= 0.05 and abs(put25[1] + 0.25) <= 0.05:
                call25_points.append((days, call25[0]))
                put25_points.append((days, put25[0]))
    return atm_points, call25_points, put25_points


def _interpolation_bracket_diagnostic(
    points: list[tuple[int, float]],
    target_days: int,
) -> dict[str, Any]:
    """Describe the exact valid observations bracketing a target maturity."""
    ordered = sorted(
        (days, iv)
        for days, iv in points
        if days > 0 and math.isfinite(iv) and iv > 0
    )
    exact = [(days, iv) for days, iv in ordered if days == target_days]
    lower = [(days, iv) for days, iv in ordered if days < target_days]
    upper = [(days, iv) for days, iv in ordered if days > target_days]
    lower_point = lower[-1] if lower else None
    upper_point = upper[0] if upper else None
    if exact:
        status = "exact"
        exact_point = exact[-1]
        lower_point = exact_point
        upper_point = exact_point
    elif lower_point is not None and upper_point is not None:
        status = "interpolated"
    elif lower_point is None and upper_point is None:
        status = "missing_both_brackets"
    elif lower_point is None:
        status = "missing_lower_bracket"
    else:
        status = "missing_upper_bracket"

    def point_payload(point: tuple[int, float] | None) -> dict[str, float | int] | None:
        if point is None:
            return None
        return {"days_to_expiry": point[0], "iv": point[1]}

    return {
        "target_days": target_days,
        "status": status,
        "lower": point_payload(lower_point),
        "upper": point_payload(upper_point),
    }


def _option_features_with_diagnostics(
    rows: list[tuple[Any, ...]],
    *,
    session: date,
) -> tuple[dict[str, float] | None, list[str]]:
    """Return option features and explicit reasons when the snapshot is incomplete."""
    atm_points, call25_points, put25_points = _option_surface_points(rows, session=session)

    iv30 = _interpolate_total_variance(atm_points, 30)
    iv90 = _interpolate_total_variance(atm_points, 90)
    call25_30 = _interpolate_total_variance(call25_points, 30)
    put25_30 = _interpolate_total_variance(put25_points, 30)
    missing: list[str] = []
    if iv30 is None:
        missing.append("missing_iv30_atm_bracket")
    if iv90 is None:
        missing.append("missing_iv90_atm_bracket")
    if call25_30 is None:
        missing.append("missing_call25_30d_bracket")
    if put25_30 is None:
        missing.append("missing_put25_30d_bracket")
    if missing:
        return None, missing
    assert iv30 is not None and iv90 is not None
    assert call25_30 is not None and put25_30 is not None
    return {
        "iv30_minus_iv90": iv30 - iv90,
        "rr25": call25_30 - put25_30,
    }, []


def _option_features_for_snapshot(
    rows: list[tuple[Any, ...]],
    *,
    session: date,
) -> dict[str, float] | None:
    """Compatibility wrapper for callers that need only the calculated features."""
    features, _missing = _option_features_with_diagnostics(rows, session=session)
    return features


def _option_snapshot_profile(
    rows: list[tuple[Any, ...]],
    *,
    session: date,
) -> dict[str, Any]:
    """Describe expiry/side/IV/delta composition without changing eligibility."""
    by_expiry: dict[date, list[tuple[Any, Any, Any]]] = defaultdict(list)
    for expiry, option_type, iv, delta in rows:
        if expiry is None:
            continue
        expiry_date = expiry.date() if isinstance(expiry, datetime) else expiry
        by_expiry[expiry_date].append((option_type, iv, delta))

    expiry_profiles: list[dict[str, Any]] = []
    for expiry in sorted(by_expiry):
        days = (expiry - session).days
        expiry_rows = by_expiry[expiry]
        side_rows = {
            side: [
                row for row in expiry_rows
                if _normalise_option_type(row[0]) == side
            ]
            for side in ("CALL", "PUT")
        }
        valid_iv = [
            float(iv)
            for _side, iv, _delta in expiry_rows
            if iv is not None and math.isfinite(float(iv)) and 0.001 <= float(iv) <= 5.0
        ]
        side_delta_ranges: dict[str, dict[str, float | None]] = {}
        side_counts: dict[str, int] = {}
        for side, side_values in side_rows.items():
            deltas = [
                float(delta)
                for _kind, _iv, delta in side_values
                if delta is not None and math.isfinite(float(delta)) and -1.0 <= float(delta) <= 1.0
            ]
            side_counts[side.lower()] = len(side_values)
            side_delta_ranges[side.lower()] = {
                "minimum": min(deltas) if deltas else None,
                "maximum": max(deltas) if deltas else None,
            }

        call25 = any(
            iv is not None and delta is not None
            and math.isfinite(float(iv)) and 0.001 <= float(iv) <= 5.0
            and math.isfinite(float(delta)) and abs(float(delta) - 0.25) <= 0.05
            for _kind, iv, delta in side_rows["CALL"]
        )
        put25 = any(
            iv is not None and delta is not None
            and math.isfinite(float(iv)) and 0.001 <= float(iv) <= 5.0
            and math.isfinite(float(delta)) and abs(float(delta) + 0.25) <= 0.05
            for _kind, iv, delta in side_rows["PUT"]
        )
        atm_call = any(
            iv is not None and delta is not None
            and math.isfinite(float(iv)) and 0.001 <= float(iv) <= 5.0
            and math.isfinite(float(delta)) and abs(float(delta) - 0.50) <= 0.10
            for _kind, iv, delta in side_rows["CALL"]
        )
        atm_put = any(
            iv is not None and delta is not None
            and math.isfinite(float(iv)) and 0.001 <= float(iv) <= 5.0
            and math.isfinite(float(delta)) and abs(float(delta) + 0.50) <= 0.10
            for _kind, iv, delta in side_rows["PUT"]
        )
        expiry_profiles.append(
            {
                "expiry": expiry.isoformat(),
                "days_to_expiry": days,
                "rows": len(expiry_rows),
                "calls": side_counts["call"],
                "puts": side_counts["put"],
                "valid_iv_rows": len(valid_iv),
                "call_delta_range": side_delta_ranges["call"],
                "put_delta_range": side_delta_ranges["put"],
                "has_atm_call": atm_call,
                "has_atm_put": atm_put,
                "has_call25": call25,
                "has_put25": put25,
            }
        )

    atm_points, call25_points, put25_points = _option_surface_points(rows, session=session)
    return {
        "rows": len(rows),
        "expiry_count": len(expiry_profiles),
        "expiry_profiles": expiry_profiles,
        "interpolation_brackets": {
            "iv30_atm": _interpolation_bracket_diagnostic(atm_points, 30),
            "iv90_atm": _interpolation_bracket_diagnostic(atm_points, 90),
            "call25_30d": _interpolation_bracket_diagnostic(call25_points, 30),
            "put25_30d": _interpolation_bracket_diagnostic(put25_points, 30),
        },
    }


def _load_option_features(
    conn: Any,
    *,
    end_date: date,
) -> tuple[dict[date, dict[str, float]], dict[str, Any]]:
    if not _table_exists(conn, "option_stream"):
        return {}, {
            "table": "option_stream",
            "available": False,
            "sessions_with_rows": 0,
            "sessions_with_30d_90d_term_and_25d_skew": 0,
            "snapshot_sessions": [],
            "rejection_reason_counts": {},
            "rejected_sessions": [],
            "snapshot_profiles": [],
        }

    rows = conn.execute(
        """
        SELECT
            run_id,
            ts,
            CAST(timezone('Asia/Kolkata', ts) AS DATE) AS session,
            expiry,
            option_type,
            iv,
            delta
        FROM option_stream
        WHERE underlying = 'NIFTY'
          AND ts IS NOT NULL
          AND CAST(timezone('Asia/Kolkata', ts) AS DATE) <= ?
        ORDER BY session, ts, run_id
        """,
        [end_date],
    ).fetchall()

    latest: dict[date, tuple[datetime, str, list[tuple[Any, ...]]]] = {}
    for run_id, ts, session, expiry, option_type, iv, delta in rows:
        run_key = str(run_id or "")
        current = latest.get(session)
        if current is None or ts > current[0] or (ts == current[0] and run_key > current[1]):
            latest[session] = (ts, run_key, [(expiry, option_type, iv, delta)])
        elif ts == current[0] and run_key == current[1]:
            current[2].append((expiry, option_type, iv, delta))

    features: dict[date, dict[str, float]] = {}
    rejection_reason_counts: dict[str, int] = defaultdict(int)
    rejected_sessions: list[dict[str, Any]] = []
    snapshot_profiles: list[dict[str, Any]] = []
    for session, (_ts, _run_id, snapshot_rows) in latest.items():
        profile = _option_snapshot_profile(snapshot_rows, session=session)
        snapshot_profiles.append({"session": session.isoformat(), **profile})
        calculated, missing = _option_features_with_diagnostics(snapshot_rows, session=session)
        if calculated is not None:
            features[session] = calculated
        else:
            for reason in missing:
                rejection_reason_counts[reason] += 1
            rejected_sessions.append(
                {"session": session.isoformat(), "reasons": missing, **profile}
            )

    summary = {
        "table": "option_stream",
        "available": True,
        "rows_read": len(rows),
        "sessions_with_rows": len(latest),
        "sessions_with_30d_90d_term_and_25d_skew": len(features),
        "snapshot_sessions": [session.isoformat() for session in sorted(latest)],
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "rejected_sessions": sorted(rejected_sessions, key=lambda item: item["session"]),
        "snapshot_profiles": sorted(snapshot_profiles, key=lambda item: item["session"]),
        "snapshot_selection": "latest run_id/ts per IST session; no fallback to older snapshots",
        "term_structure": "30D and 90D constant-maturity ATM IV interpolated in total-variance space; no extrapolation",
        "rr25": (
            "30D constant-maturity call 25-delta IV minus put 25-delta IV; "
            "total-variance interpolation; no extrapolation"
        ),
    }
    return features, summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_calibration_dataset(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    if not args.db_path.is_file():
        raise FileNotFoundError(args.db_path)
    as_of = args.as_of or datetime.now(IST).date()
    end_date = min(args.end_date or (as_of - timedelta(days=1)), as_of - timedelta(days=1))
    if args.min_intraday_observations < 2:
        raise ValueError("invalid_export_coverage_threshold")
    if args.output.resolve() in {args.db_path.resolve(), args.india_vix_csv.resolve()}:
        raise ValueError("output_path_must_not_overwrite_a_source")
    if args.manifest.resolve() in {args.db_path.resolve(), args.india_vix_csv.resolve(), args.output.resolve()}:
        raise ValueError("manifest_path_must_be_distinct_from_sources_and_csv")
    if args.iv_lookback_sessions < 2 or args.iv_min_observations < 2:
        raise ValueError("invalid_iv_percentile_configuration")

    ivp, vix_summary = _load_india_vix(
        args.india_vix_csv,
        lookback_sessions=args.iv_lookback_sessions,
        minimum_observations=args.iv_min_observations,
        end_date=end_date,
    )
    db_hash = _sha256(args.db_path)
    store = DuckDBStore(path=args.db_path, read_only=True)
    try:
        bars, daily_summary = _load_daily_bars(store.conn, end_date=end_date)
        price = _price_features(bars)
        realized_variance, rv_summary = _load_realized_variance(
            store.conn,
            end_date=end_date,
            minimum_observations=args.min_intraday_observations,
        )
        options, options_summary = _load_option_features(store.conn, end_date=end_date)
    finally:
        store.close()

    output_rows: list[dict[str, Any]] = []
    missing_counts = {column: 0 for column in CSV_COLUMNS if column != "session"}
    candidate_sessions = [bar.trade_date for bar in bars]
    candidate_session_set = set(candidate_sessions)
    snapshot_session_set = {
        date.fromisoformat(value)
        for value in options_summary.get("snapshot_sessions", [])
    }
    candidate_sessions_with_snapshot = candidate_session_set & snapshot_session_set
    candidate_sessions_with_complete_surface = candidate_session_set & set(options)
    candidate_sessions_with_price_features = candidate_session_set & set(price)
    candidate_sessions_with_ivp = candidate_session_set & set(ivp)
    candidate_sessions_with_realized_variance = candidate_session_set & set(realized_variance)
    candidate_sessions_with_all_source_components = (
        candidate_session_set
        & set(price)
        & set(ivp)
        & set(options)
        & set(realized_variance)
    )
    candidate_sessions_rejected = {
        date.fromisoformat(item["session"])
        for item in options_summary.get("rejected_sessions", [])
    } & candidate_session_set
    candidate_rejection_reason_counts: dict[str, int] = defaultdict(int)
    for item in options_summary.get("rejected_sessions", []):
        if date.fromisoformat(item["session"]) in candidate_session_set:
            for reason in item["reasons"]:
                candidate_rejection_reason_counts[reason] += 1

    for session in candidate_sessions:
        price_values = price.get(session)
        option_values = options.get(session)
        values: dict[str, Any] = {
            "ivp": ivp.get(session),
            "iv30_minus_iv90": option_values.get("iv30_minus_iv90") if option_values else None,
            "rr25": option_values.get("rr25") if option_values else None,
            "realized_variance": realized_variance.get(session),
        }
        for key in (
            "adx14",
            "plus_di14",
            "minus_di14",
            "er20",
            "chop14",
            "atr14",
            "atr_percentile",
            "bandwidth_percentile",
            "range_position",
            "change20",
            "sma20_slope",
        ):
            values[key] = price_values.get(key) if price_values else None

        missing = [key for key, value in values.items() if value is None or not math.isfinite(float(value))]
        for key in missing:
            missing_counts[key] += 1
        if missing:
            continue
        output_rows.append(
            {
                "session": session.isoformat(),
                **{key: float(value) for key, value in values.items()},
            }
        )

    output_rows.sort(key=lambda row: row["session"])
    _write_csv(args.output, output_rows)

    ready = len(output_rows) >= MINIMUM_CALIBRATION_SESSIONS
    manifest: dict[str, Any] = {
        "export_version": EXPORT_VERSION,
        "feature_contract": FEATURE_CONTRACT,
        "underlying": "NIFTY",
        "status": "READY_FOR_DIAGNOSTIC_CALIBRATION" if ready else "INSUFFICIENT_SOURCE_COVERAGE",
        "calibration_ready": ready,
        "mode": "diagnostic_only",
        "decision_eligibility_asserted": False,
        "paper_trading_approval_asserted": False,
        "thresholds_changed": False,
        "thresholds_promoted": False,
        "point_in_time": True,
        "no_lookahead": True,
        "no_forward_fill": True,
        "no_term_structure_extrapolation": True,
        "automatic_promotion": False,
        "as_of_exclusive": as_of.isoformat(),
        "end_date_inclusive": end_date.isoformat(),
        "minimum_complete_sessions": MINIMUM_CALIBRATION_SESSIONS,
        "complete_sessions_exported": len(output_rows),
        "output_csv": {
            "path": str(args.output),
            "sha256": _sha256(args.output),
            "rows": len(output_rows),
        },
        "candidate_daily_sessions": len(candidate_sessions),
        "first_exported_session": output_rows[0]["session"] if output_rows else None,
        "last_exported_session": output_rows[-1]["session"] if output_rows else None,
        "csv_columns": CSV_COLUMNS,
        "missing_feature_session_counts": missing_counts,
        "coverage_bottlenecks": {
            "candidate_daily_sessions": len(candidate_sessions),
            "daily_price_feature_sessions": len(price),
            "india_vix_ivp_sessions": len(ivp),
            "option_surface_sessions": len(options),
            "option_sessions_without_snapshot": len(
                candidate_session_set - snapshot_session_set
            ),
            "option_sessions_rejected_for_incomplete_surface": len(candidate_sessions_rejected),
            "option_surface_rejection_reason_counts": dict(
                sorted(candidate_rejection_reason_counts.items())
            ),
            "candidate_sessions_with_snapshot": len(candidate_sessions_with_snapshot),
            "candidate_sessions_with_complete_surface": len(candidate_sessions_with_complete_surface),
            "candidate_sessions_with_incomplete_surface": len(candidate_sessions_rejected),
            "snapshot_sessions_outside_candidate_window": len(
                snapshot_session_set - candidate_session_set
            ),
            "candidate_sessions_with_price_features": len(candidate_sessions_with_price_features),
            "candidate_sessions_with_ivp": len(candidate_sessions_with_ivp),
            "candidate_sessions_with_realized_variance": len(
                candidate_sessions_with_realized_variance
            ),
            "candidate_sessions_with_all_source_components": len(
                candidate_sessions_with_all_source_components
            ),
            "realized_variance_sessions": len(realized_variance),
            "complete_session_upper_bound": len(candidate_sessions_with_all_source_components),
            "daily_bars_required_for_423_price_feature_sessions": 688,
            "india_vix_sessions_required_for_423_ivp_sessions": 452,
            "option_surface_sessions_required": MINIMUM_CALIBRATION_SESSIONS,
            "realized_variance_sessions_required": MINIMUM_CALIBRATION_SESSIONS,
        },
        "sources": {
            "duckdb": {
                "path": str(args.db_path),
                "sha256": db_hash,
                "read_only": True,
                "daily_ohlc": daily_summary,
                "intraday_realized_variance": rv_summary,
                "option_surface": options_summary,
            },
            "india_vix": vix_summary,
        },
        "feature_definitions": {
            "ivp": "point-in-time trailing percentile rank of India VIX Close",
            "iv30_minus_iv90": "30D constant-maturity ATM IV minus 90D constant-maturity ATM IV",
            "rr25": "30D constant-maturity 25-delta call IV minus 25-delta put IV",
            "price_action": "same daily-bar calculations as institutional_regime_price_action_v5",
            "realized_variance": "sum of squared within-session 1-minute log returns; not annualized",
        },
        "coverage_notes": [
            "Only sessions with all 16 required fields are exported.",
            "Missing values are not imputed, forward-filled, or synthesized.",
            "India VIX Close is used as the IVP proxy; it is not represented as option-implied ATM IV.",
            (
                "The daily_rv_observations.rv field and daily_rv_NIFTY.csv are not used "
                "because the prior audit did not establish their units as non-annualized realized variance."
            ),
            (
                "The option surface is derived only from the latest available legacy "
                "option_stream snapshot per IST session."
            ),
            "No output from this exporter changes regime thresholds, publication status, or trading authority.",
        ],
    }
    _write_json(args.manifest, manifest)
    return (0 if ready else 2), manifest


def main() -> int:
    args = _parser().parse_args()
    status, manifest = export_calibration_dataset(args)
    print(f"status={manifest['status']}")
    print(f"complete_sessions={manifest['complete_sessions_exported']}")
    print(f"minimum_required_sessions={manifest['minimum_complete_sessions']}")
    print(f"csv={args.output}")
    print(f"manifest={args.manifest}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
