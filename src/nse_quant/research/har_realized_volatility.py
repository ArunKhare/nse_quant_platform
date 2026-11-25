"""Point-in-time 30-calendar-day HAR-RV forecast from complete NSE 5-minute bars.

One-minute candles must cover the entire regular NSE session. Five-minute
intraday variance is sampled from complete minute bars; overnight return is
measured from the prior session close to the current session open. No gaps are
bridged.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np

from nse_quant.core.constants import IST
from nse_quant.core.trading_calendar import NSETradingCalendar

HAR_RV_METHOD = "har_rv_5m_intraday_plus_overnight"
HAR_RV_VERSION = "har_rv_30d_v1"
HAR_RV_HORIZON_DAYS = 30
HAR_RV_MEASURE = "sum_squared_5m_log_returns_plus_squared_overnight_return"
TRADING_DAYS_PER_YEAR = 252
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)
MINUTES_PER_SESSION = 375
HAR_WEEK_DAYS = 5
HAR_MONTH_DAYS = 22
HAR_TRAINING_WINDOW = 252
HAR_FORECAST_SESSIONS = 21
HAR_RV_CALIBRATION_VERSION = "har_rv_30d_calibration_v1"
CALIBRATION_MINIMUM_SAMPLES = 30
CALIBRATION_MAXIMUM_ORIGINS = 60


@dataclass(frozen=True)
class DailyRVObservation:
    session_date: date
    overnight_return: float
    intraday_variance: float
    realized_variance: float
    source_minute_rows: int
    first_minute_ts: datetime
    last_minute_ts: datetime


def _finite_positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def build_daily_rv_observations(
    candles: Sequence[tuple[datetime, float, float]],
    *,
    calendar: NSETradingCalendar,
    as_of: datetime,
) -> tuple[DailyRVObservation, ...]:
    """Build complete-session RV from (minute_start, open, close) rows."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("aware_as_of_required")
    cutoff = as_of.astimezone(IST)
    grouped: dict[date, dict[datetime, tuple[float, float]]] = defaultdict(dict)
    for timestamp, open_price, close_price in candles:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("aware_candle_timestamp_required")
        local = timestamp.astimezone(IST)
        if not REGULAR_OPEN <= local.time().replace(tzinfo=None) < REGULAR_CLOSE:
            continue
        if local.second or local.microsecond:
            raise ValueError("minute_candle_timestamp_must_be_on_minute")
        if not _finite_positive(open_price) or not _finite_positive(close_price):
            raise ValueError("finite_positive_minute_prices_required")
        instant = local.replace(second=0, microsecond=0)
        if instant >= cutoff:
            continue
        if instant in grouped[local.date()]:
            raise ValueError("duplicate_minute_candle")
        grouped[local.date()][instant] = (float(open_price), float(close_price))

    complete: dict[date, tuple[float, float, float, datetime, datetime]] = {}
    for day, rows in grouped.items():
        session = calendar.session_for_date(day)
        if session is None or session.open_time != REGULAR_OPEN or session.close_time != REGULAR_CLOSE:
            continue
        expected = [
            datetime.combine(day, REGULAR_OPEN, tzinfo=IST) + timedelta(minutes=i)
            for i in range(MINUTES_PER_SESSION)
        ]
        if len(rows) != MINUTES_PER_SESSION or any(ts not in rows for ts in expected):
            continue
        if session.closes_at > cutoff:
            continue
        minute_rows = [rows[ts] for ts in expected]
        first_open = minute_rows[0][0]
        five_minute_closes = [minute_rows[index][1] for index in range(4, MINUTES_PER_SESSION, 5)]
        previous_price = first_open
        intraday_variance = 0.0
        for close_price in five_minute_closes:
            log_return = math.log(close_price / previous_price)
            intraday_variance += log_return * log_return
            previous_price = close_price
        if not math.isfinite(intraday_variance):
            raise ValueError("non_finite_intraday_realized_variance")
        complete[day] = (
            first_open, minute_rows[-1][1], intraday_variance, expected[0], expected[-1]
        )

    observations: list[DailyRVObservation] = []
    for day in sorted(complete):
        previous_sessions = calendar.sessions_between(day - timedelta(days=10), day - timedelta(days=1))
        if not previous_sessions:
            continue
        prior = complete.get(previous_sessions[-1].session_date)
        if prior is None:
            # Missing complete sessions are never interpreted as overnight gaps.
            continue
        first_open, _session_close, intraday_variance, first_ts, last_ts = complete[day]
        overnight_return = math.log(first_open / prior[1])
        if not math.isfinite(overnight_return):
            raise ValueError("non_finite_overnight_return")
        observations.append(
            DailyRVObservation(
                session_date=day,
                overnight_return=overnight_return,
                intraday_variance=intraday_variance,
                realized_variance=intraday_variance + overnight_return * overnight_return,
                source_minute_rows=MINUTES_PER_SESSION,
                first_minute_ts=first_ts,
                last_minute_ts=last_ts,
            )
        )
    return tuple(observations)


def _har_design(values: Sequence[float], target_index: int) -> tuple[float, float, float, float]:
    prior = values[:target_index]
    return (
        1.0,
        prior[-1],
        float(np.mean(prior[-HAR_WEEK_DAYS:])),
        float(np.mean(prior[-HAR_MONTH_DAYS:])),
    )


def _fit_har(values: Sequence[float], *, training_window: int) -> tuple[np.ndarray, dict[str, object]]:
    if len(values) < training_window + HAR_MONTH_DAYS:
        raise ValueError("insufficient_har_rv_history")
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("invalid_daily_realized_variance")
    start = len(values) - training_window
    x = np.asarray(
        [_har_design(values, index) for index in range(start, len(values))], dtype=np.float64
    )
    y = np.asarray(values[start:], dtype=np.float64)
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(x, y, rcond=None)
    if rank < x.shape[1] or not np.all(np.isfinite(coefficients)):
        raise ValueError("har_rv_design_matrix_rank_deficient")
    residuals = y - x @ coefficients
    total = float(np.sum((y - float(np.mean(y))) ** 2))
    return coefficients, {
        "training_observations": float(len(y)),
        "training_r_squared": 1.0 - float(np.sum(residuals**2)) / total if total > 0 else 0.0,
        "training_rmse_daily_variance": float(math.sqrt(float(np.mean(residuals**2)))),
    }


def _forecast_daily_variances(
    history: Sequence[float], *, horizon_sessions: int, training_window: int
) -> tuple[list[float], dict[str, object]]:
    coefficients, fit = _fit_har(history, training_window=training_window)
    projected = [float(value) for value in history]
    forecasts: list[float] = []
    for _ in range(horizon_sessions):
        value = float(np.asarray(_har_design(projected, len(projected))) @ coefficients)
        if not math.isfinite(value):
            raise ValueError("non_finite_har_rv_forecast")
        value = max(0.0, value)
        forecasts.append(value)
        projected.append(value)
    fit["coefficients"] = [float(value) for value in coefficients]
    return forecasts, fit


def forecast_har_rv_30d(
    daily_realized_variances: Sequence[float],
    *,
    training_window: int = HAR_TRAINING_WINDOW,
    horizon_sessions: int = HAR_FORECAST_SESSIONS,
) -> tuple[float | None, dict[str, object]]:
    """Forecast annualized 30-calendar-day RV volatility (21 NSE sessions)."""
    details: dict[str, object] = {
        "method": HAR_RV_METHOD, "version": HAR_RV_VERSION,
        "horizon_days": HAR_RV_HORIZON_DAYS, "horizon_sessions": horizon_sessions,
        "measure": HAR_RV_MEASURE, "is_forecast": True,
        "gate_eligible": False, "diagnostic_only": True,
        "training_window": training_window,
        "minimum_observations": training_window + HAR_MONTH_DAYS,
        "observations_available": len(daily_realized_variances),
        "annualization_days": TRADING_DAYS_PER_YEAR,
    }
    if horizon_sessions < 1 or training_window < 60:
        details["reason"] = "invalid_har_configuration"
        return None, details
    if len(daily_realized_variances) < training_window + HAR_MONTH_DAYS:
        details["reason"] = "insufficient_har_rv_history"
        return None, details
    try:
        forecasts, fit = _forecast_daily_variances(
            daily_realized_variances, horizon_sessions=horizon_sessions,
            training_window=training_window
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        details["reason"] = str(exc)
        return None, details
    mean_daily_variance = float(np.mean(forecasts))
    annualized_variance = mean_daily_variance * TRADING_DAYS_PER_YEAR
    volatility = math.sqrt(annualized_variance)
    details.update({
        "reason": None, "forecast_daily_variances": forecasts,
        "forecast_mean_daily_variance": mean_daily_variance,
        "forecast_annualized_variance": annualized_variance,
        "forecast_annualized_volatility": volatility,
        "forecast_variance_sum": float(sum(forecasts)),
        "model": "har_rv_level_ols_v1", **fit,
    })
    return volatility, details


def calibrate_har_rv_forecast_errors(
    daily_realized_variances: Sequence[float],
    *,
    training_window: int = HAR_TRAINING_WINDOW,
    horizon_sessions: int = HAR_FORECAST_SESSIONS,
    minimum_samples: int = CALIBRATION_MINIMUM_SAMPLES,
) -> dict[str, object]:
    """Walk-forward error calibration; expose a gate margin only after 30 origins."""
    if any(not math.isfinite(value) or value < 0.0 for value in daily_realized_variances):
        return {
            "method": "rolling_origin_absolute_annualized_variance_error",
            "version": HAR_RV_CALIBRATION_VERSION,
            "minimum_samples": minimum_samples,
            "samples": 0,
            "horizon_sessions": horizon_sessions,
            "error_quantile": 0.90,
            "gate_margin_eligible": False,
            "diagnostic_only": True,
            "reason": "invalid_daily_realized_variance",
            "absolute_error_p90": None,
            "mean_absolute_error": None,
        }
    errors: list[float] = []
    latest_origin = len(daily_realized_variances) - horizon_sessions
    earliest_origin = training_window + HAR_MONTH_DAYS
    first_origin = max(earliest_origin, latest_origin - CALIBRATION_MAXIMUM_ORIGINS + 1)
    for origin in range(first_origin, latest_origin + 1):
        try:
            forecasts, _fit = _forecast_daily_variances(
                daily_realized_variances[:origin],
                horizon_sessions=horizon_sessions, training_window=training_window
            )
        except (ValueError, np.linalg.LinAlgError):
            continue
        forecast_var = float(np.mean(forecasts)) * TRADING_DAYS_PER_YEAR
        realized_var = (
            float(np.mean(daily_realized_variances[origin:origin + horizon_sessions]))
            * TRADING_DAYS_PER_YEAR
        )
        errors.append(abs(realized_var - forecast_var))
    result: dict[str, object] = {
        "method": "rolling_origin_absolute_annualized_variance_error",
        "version": HAR_RV_CALIBRATION_VERSION, "minimum_samples": minimum_samples,
        "samples": len(errors), "horizon_sessions": horizon_sessions,
        "error_quantile": 0.90, "gate_margin_eligible": False, "diagnostic_only": True,
    }
    if len(errors) < minimum_samples:
        result.update({
            "reason": "insufficient_walk_forward_calibration_samples",
            "absolute_error_p90": None, "mean_absolute_error": None,
        })
        return result
    result.update({
        "reason": None, "absolute_error_p90": float(np.quantile(errors, 0.90)),
        "mean_absolute_error": float(np.mean(errors)),
        "gate_margin_eligible": True, "diagnostic_only": False,
    })
    return result
