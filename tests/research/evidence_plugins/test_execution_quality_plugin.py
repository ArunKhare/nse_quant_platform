"""Tests for observational snapshot quote quality."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.core.settings import ExecutionQualitySettings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.execution_quality import (
    ExecutionQualityPlugin,
)
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)

TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
EXPIRY = date(2026, 11, 5)


def make_quote(
    token: int = 101,
    /,
    **updates: Any,
) -> OptionQuote:
    instrument = Instrument(
        tradingsymbol=f"NIFTY-{token}",
        instrument_token=token,
        underlying="NIFTY",
        expiry=EXPIRY,
        strike=24_000.0,
        option_type=OptionType.CE,
        lot_size=1,
    )

    values: dict[str, Any] = {
        "instrument": instrument,
        "instrument_token": token,
        "bid": 99.0,
        "ask": 101.0,
        "oi": 100_000,
        "volume": 500,
        "exchange_ts": TS,
        "trade_ts": TS,
        "received_at": TS,
    }
    values.update(updates)
    return OptionQuote(**values)


def make_snapshot(
    quotes: list[OptionQuote],
    *,
    ts: datetime = TS,
) -> ChainSnapshot:
    return ChainSnapshot(
        ts=ts,
        underlying="NIFTY",
        spot=24_000.0,
        expiry=EXPIRY,
        quotes=quotes,
    )


def make_context(
    snapshot: ChainSnapshot | None,
    *,
    ts: datetime = TS,
) -> DecisionContext:
    return DecisionContext(
        run_id="execution-quality-test",
        symbol="NIFTY",
        ts=ts,
        features=None,
        snapshot=snapshot,
        iv_history_count=0,
        current_regime=None,
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def plugin() -> ExecutionQualityPlugin:
    return ExecutionQualityPlugin(
        settings=ExecutionQualitySettings(
            max_quote_age_seconds=300,
        )
    )


def evaluate(quote: OptionQuote) -> dict[str, Any]:
    return plugin().build(make_context(make_snapshot([quote])))


def test_valid_quote_is_complete() -> None:
    result = evaluate(make_quote())

    assert result["available"] is True
    assert result["complete"] is True
    assert result["total_quotes"] == 1
    assert result["usable_quotes"] == 1
    assert result["spread_summary"]["sample_count"] == 1
    assert result["spread_summary"]["mean_fraction"] == pytest.approx(0.02)
    assert result["contracts"][0]["spread_absolute"] == 2.0


def test_locked_quote_has_zero_spread() -> None:
    result = evaluate(make_quote(bid=100.0, ask=100.0))

    assert result["complete"] is True
    assert result["spread_summary"]["max_fraction"] == 0.0


@pytest.mark.parametrize(
    ("bid", "ask", "reason"),
    [
        (None, 101.0, "missing_bid_ask"),
        (99.0, None, "missing_bid_ask"),
        (0.0, 101.0, "non_positive_bid_ask"),
        (-1.0, 101.0, "non_positive_bid_ask"),
        (102.0, 101.0, "crossed_bid_ask"),
        (float("nan"), 101.0, "non_finite_bid_ask"),
        (99.0, float("inf"), "non_finite_bid_ask"),
    ],
)
def test_invalid_prices_are_excluded(
    bid: float | None,
    ask: float | None,
    reason: str,
) -> None:
    result = evaluate(make_quote(bid=bid, ask=ask))

    assert result["available"] is True
    assert result["complete"] is False
    assert result["valid_two_sided_quotes"] == 0
    assert result["usable_quotes"] == 0
    assert result["spread_summary"]["mean_fraction"] is None
    assert result["contracts"][0]["price_reason"] == reason

    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    ("age", "status", "usable"),
    [
        (0, "fresh", True),
        (300, "fresh", True),
        (301, "stale", False),
        (-1, "future", False),
    ],
)
def test_exchange_freshness(
    age: int,
    status: str,
    usable: bool,
) -> None:
    result = evaluate(make_quote(exchange_ts=TS - timedelta(seconds=age)))

    assert result["contracts"][0]["exchange"]["status"] == status
    assert result["contracts"][0]["usable"] is usable


def test_missing_exchange_time_is_not_receipt_freshness() -> None:
    result = evaluate(make_quote(exchange_ts=None))

    assert result["contracts"][0]["receipt"]["status"] == "fresh"
    assert result["contracts"][0]["exchange"]["status"] == "missing"
    assert result["usable_quotes"] == 0
    assert result["complete"] is False


@pytest.mark.parametrize("field", ["exchange_ts", "received_at"])
def test_naive_quote_timestamps_are_invalid(field: str) -> None:
    result = evaluate(make_quote(**{field: TS.replace(tzinfo=None)}))

    assert result["usable_quotes"] == 0
    assert result["complete"] is False


def test_future_receipt_is_excluded() -> None:
    result = evaluate(make_quote(received_at=TS + timedelta(seconds=1)))

    assert result["receipt_timestamp_counts"]["future"] == 1
    assert result["usable_quotes"] == 0


def test_old_trade_does_not_replace_quote_freshness() -> None:
    result = evaluate(make_quote(trade_ts=TS - timedelta(days=1)))

    assert result["trade_timestamp_counts"]["stale"] == 1
    assert result["complete"] is True


def test_future_trade_is_excluded() -> None:
    result = evaluate(make_quote(trade_ts=TS + timedelta(seconds=1)))

    assert result["usable_quotes"] == 0


@pytest.mark.parametrize("value", [None, -1])
@pytest.mark.parametrize("field", ["oi", "volume"])
def test_missing_or_invalid_participation_is_explicit(
    field: str,
    value: int | None,
) -> None:
    result = evaluate(make_quote(**{field: value}))

    assert result["usable_quotes"] == 1
    assert result["complete"] is False
    assert result[f"{field}_available_quotes"] == 0


def test_zero_oi_and_volume_are_present_values() -> None:
    result = evaluate(make_quote(oi=0, volume=0))

    assert result["complete"] is True
    assert result["oi_available_quotes"] == 1
    assert result["volume_available_quotes"] == 1


def test_summary_uses_only_usable_quotes() -> None:
    result = plugin().build(
        make_context(
            make_snapshot(
                [
                    make_quote(101),
                    make_quote(
                        102,
                        exchange_ts=TS - timedelta(seconds=301),
                    ),
                ]
            )
        )
    )

    assert result["total_quotes"] == 2
    assert result["valid_two_sided_quotes"] == 2
    assert result["usable_quotes"] == 1
    assert result["usable_quote_fraction"] == 0.5
    assert result["spread_summary"]["sample_count"] == 1
    assert result["spread_summary"]["mean_fraction"] == pytest.approx(0.02)


def test_other_expiry_is_excluded() -> None:
    other = make_quote(102)
    other.instrument = other.instrument.model_copy(update={"expiry": EXPIRY + timedelta(days=7)})

    result = plugin().build(make_context(make_snapshot([make_quote(), other])))

    assert result["total_quotes"] == 1
    assert result["complete"] is True


def test_missing_snapshot_is_unavailable() -> None:
    result = plugin().build(make_context(None))

    assert result["available"] is False
    assert result["reason"] == "missing_snapshot"


def test_empty_chain_is_unavailable() -> None:
    result = plugin().build(make_context(make_snapshot([])))

    assert result["available"] is False
    assert result["reason"] == "no_selected_expiry_quotes"


def test_future_snapshot_is_unavailable() -> None:
    result = plugin().build(
        make_context(
            make_snapshot(
                [make_quote()],
                ts=TS + timedelta(seconds=1),
            )
        )
    )

    assert result["available"] is False
    assert result["reason"] == "future_snapshot"


def test_duplicate_tokens_are_unavailable() -> None:
    result = plugin().build(make_context(make_snapshot([make_quote(), make_quote()])))

    assert result["reason"] == "duplicate_instrument_tokens"


def test_runner_contains_naive_decision_error() -> None:
    results = EvidencePluginRunner([plugin()]).run(
        make_context(
            make_snapshot([make_quote()]),
            ts=TS.replace(tzinfo=None),
        )
    )

    assert results[0].available is False
    assert results[0].payload["error_type"] == "ValueError"


def test_settings_default_to_disabled() -> None:
    assert ExecutionQualitySettings().enabled is False


@pytest.mark.parametrize("age", [0, -1])
def test_settings_reject_invalid_age(age: int) -> None:
    with pytest.raises(ValidationError):
        ExecutionQualitySettings(max_quote_age_seconds=age)


def test_payload_is_persisted(tmp_path: Path) -> None:
    store = DuckDBStore(tmp_path / "execution_quality.duckdb")

    try:
        context = make_context(make_snapshot([make_quote()]))
        result = plugin().build(context)

        store.write_decision_evidence(
            run_id=context.run_id,
            ts=context.ts,
            symbol=context.symbol,
            plugin="execution_quality",
            evidence=result,
        )

        rows = store.conn.execute(
            """
            SELECT available, payload_json
            FROM decision_evidence
            WHERE run_id = ? AND plugin = ?
            """,
            [context.run_id, "execution_quality"],
        ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] is True
        assert json.loads(rows[0][1])["usable_quotes"] == 1
    finally:
        store.close()
