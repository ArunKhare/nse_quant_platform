from __future__ import annotations

from datetime import date

import pytest

from scripts.export_institutional_regime_calibration import (
    _interpolate_total_variance,
    _load_india_vix,
    _option_features_for_snapshot,
    _parse_vix_date,
)


def test_india_vix_date_parser_accepts_nse_format() -> None:
    assert _parse_vix_date("28-NOV-2025") == date(2025, 11, 28)


def test_india_vix_percentile_is_point_in_time(tmp_path) -> None:
    source = tmp_path / "india_vix.csv"
    source.write_text(
        "Date,Open,High,Low,Close,Prev. Close,Change,% Change\n"
        "28-NOV-2025,11.785,11.785,10.8175,11.62,11.785,-0.17,-1.40\n"
        "01-DEC-2025,12.0,12.0,11.0,12.0,11.62,0.38,3.27\n"
        "02-DEC-2025,10.0,12.0,10.0,10.0,12.0,-2.0,-16.67\n",
        encoding="utf-8",
    )

    ivp, summary = _load_india_vix(
        source,
        lookback_sessions=3,
        minimum_observations=2,
        end_date=date(2025, 12, 2),
    )

    assert date(2025, 11, 28) not in ivp
    assert ivp[date(2025, 12, 1)] == pytest.approx(75.0)
    assert ivp[date(2025, 12, 2)] == pytest.approx(100.0 / 6.0)
    assert summary["rows_through_end_date"] == 3


def test_total_variance_interpolation_does_not_extrapolate() -> None:
    points = [(20, 0.20), (40, 0.24), (80, 0.30), (100, 0.32)]

    assert _interpolate_total_variance(points, 20) == pytest.approx(0.20)
    assert _interpolate_total_variance(points, 30) is not None
    assert _interpolate_total_variance(points, 10) is None
    assert _interpolate_total_variance(points, 110) is None


def test_option_snapshot_builds_term_and_rr25_only_with_bracketing_expiries() -> None:
    session = date(2025, 11, 28)
    rows = []
    for days, atm_iv, call25_iv, put25_iv in (
        (20, 0.20, 0.22, 0.24),
        (40, 0.22, 0.24, 0.26),
        (80, 0.25, 0.27, 0.29),
        (100, 0.27, 0.29, 0.31),
    ):
        expiry = date.fromordinal(session.toordinal() + days)
        rows.extend(
            [
                (expiry, "CE", atm_iv, 0.50),
                (expiry, "PE", atm_iv + 0.002, -0.50),
                (expiry, "CE", call25_iv, 0.25),
                (expiry, "PE", put25_iv, -0.25),
            ]
        )

    result = _option_features_for_snapshot(rows, session=session)

    assert result is not None
    assert result["iv30_minus_iv90"] < 0
    assert result["rr25"] < 0


def test_option_snapshot_returns_unavailable_without_90_day_bracket() -> None:
    session = date(2025, 11, 28)
    expiry = date.fromordinal(session.toordinal() + 30)
    rows = [
        (expiry, "CE", 0.20, 0.50),
        (expiry, "PE", 0.20, -0.50),
        (expiry, "CE", 0.22, 0.25),
        (expiry, "PE", 0.24, -0.25),
    ]

    assert _option_features_for_snapshot(rows, session=session) is None
