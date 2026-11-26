"""Research-only paired India VIX / NIFTY surface-IV30 proxy diagnostics."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nse_quant.research.india_vix_iv30_suitability import (
    MINIMUM_PAIRS,
    ProxyPair,
    evaluate_india_vix_iv30_proxy,
)


def _pairs(count: int) -> list[ProxyPair]:
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    result = []
    for index in range(count):
        as_of = start + timedelta(days=index)
        source = as_of - timedelta(seconds=2)
        surface_iv = 0.12 + (index % 9) * 0.002
        vix_iv = surface_iv + (0.003 if index % 2 else -0.002)
        result.append(
            ProxyPair(
                trade_date=as_of.date(),
                as_of=as_of,
                india_vix_iv30=vix_iv,
                india_vix_source_time=source,
                india_vix_received_at=source + timedelta(milliseconds=200),
                india_vix_revision_sha256=f"{index + 1:064x}",
                surface_iv30=surface_iv,
                surface_source_time=source + timedelta(seconds=1),
                surface_received_at=source + timedelta(seconds=1, milliseconds=200),
                surface_batch_sha256=f"{index + 100:064x}",
            )
        )
    return result


def test_sufficient_sample_reports_chronological_holdout_without_approval() -> None:
    result = evaluate_india_vix_iv30_proxy(_pairs(MINIMUM_PAIRS))
    assert result["assessment_status"] == "DIAGNOSTIC_ONLY_REVIEW_REQUIRED"
    assert result["suitability_asserted"] is False
    assert result["decision_eligibility_asserted"] is False
    assert result["publication_asserted"] is False
    assert result["sample"]["pairs"] == MINIMUM_PAIRS
    assert result["sample"]["calibration_pairs"] == 40
    assert result["sample"]["holdout_pairs"] == 20
    assert result["holdout_metrics"]["pairs"] == 20
    assert result["all_sample_metrics"]["mae"] > 0
    assert result["all_sample_metrics"]["rmse"] >= result["all_sample_metrics"]["mae"]


def test_insufficient_sample_never_claims_suitability() -> None:
    result = evaluate_india_vix_iv30_proxy(_pairs(25))
    assert result["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["suitability_asserted"] is False
    assert result["sample"]["sessions"] == 25


def test_unsynchronized_pair_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[1] = replace(
        pairs[1],
        surface_source_time=pairs[1].surface_source_time + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="SYNCHRONIZED_SOURCE_PAIR_REQUIRED"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_future_received_quote_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[1] = replace(
        pairs[1],
        india_vix_received_at=pairs[1].as_of + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="FUTURE_OR_UNORDERED_SOURCE_CLOCK"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_non_internal_surface_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[0] = replace(pairs[0], surface_iv_source="india_vix")
    with pytest.raises(ValueError, match="INTERNAL_CM_OBSERVATION_SURFACE_REQUIRED"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_surface_decision_authority_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[0] = replace(pairs[0], surface_decision_eligibility_asserted=True)
    with pytest.raises(ValueError, match="INTERNAL_CM_OBSERVATION_SURFACE_REQUIRED"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_invalid_source_revision_pin_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[0] = replace(pairs[0], india_vix_revision_sha256="not-a-pin")
    with pytest.raises(ValueError, match="INDIA_VIX_REVISION_SHA256_REQUIRED"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_out_of_order_or_duplicate_as_of_is_rejected() -> None:
    pairs = _pairs(3)
    pairs[2] = replace(pairs[2], as_of=pairs[1].as_of)
    with pytest.raises(ValueError, match="STRICTLY_ORDERED_UNIQUE_AS_OF_REQUIRED"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_non_nifty_underlying_is_rejected() -> None:
    pairs = _pairs(2)
    pairs[0] = replace(pairs[0], underlying="BANKNIFTY")
    with pytest.raises(ValueError, match="NIFTY_PROXY_COMPARISON_ONLY"):
        evaluate_india_vix_iv30_proxy(pairs)


def test_invalid_holdout_fraction_is_rejected() -> None:
    with pytest.raises(ValueError, match="HOLDOUT_FRACTION_OUT_OF_RANGE"):
        evaluate_india_vix_iv30_proxy(_pairs(2), holdout_fraction=0.05)


def test_holdout_split_keeps_each_trading_session_wholly_on_one_side() -> None:
    base = _pairs(20)
    intraday = []
    for day_index, first in enumerate(base):
        for sample_index in range(3):
            as_of = first.as_of + timedelta(hours=sample_index)
            source = as_of - timedelta(seconds=2)
            intraday.append(
                replace(
                    first,
                    as_of=as_of,
                    india_vix_source_time=source,
                    india_vix_received_at=source + timedelta(milliseconds=200),
                    india_vix_revision_sha256=f"{day_index * 3 + sample_index + 1:064x}",
                    surface_source_time=source + timedelta(seconds=1),
                    surface_received_at=source + timedelta(seconds=1, milliseconds=200),
                    surface_batch_sha256=f"{day_index * 3 + sample_index + 100:064x}",
                )
            )
    result = evaluate_india_vix_iv30_proxy(intraday)
    assert result["sample"]["pairs"] == 60
    assert result["sample"]["calibration_pairs"] == 39
    assert result["sample"]["holdout_pairs"] == 21


def test_trade_date_must_match_as_of_in_ist() -> None:
    pairs = _pairs(2)
    pairs[0] = replace(pairs[0], trade_date=pairs[0].trade_date + timedelta(days=1))
    with pytest.raises(ValueError, match="TRADE_DATE_DOES_NOT_MATCH_AS_OF_IST"):
        evaluate_india_vix_iv30_proxy(pairs)
