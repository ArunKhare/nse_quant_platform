from datetime import UTC, date, datetime

import pytest

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.regime_policy import RegimePolicy

CANONICAL = "HIGH_IV_CONTANGO_NORMAL_SKEW_HIGH_VOL_CHOP"


def test_daily_iv_and_legacy_market_context_use_separate_vocabularies(tmp_path):
    store = DuckDBStore(tmp_path / "regime-vocabulary.duckdb")
    observed_at = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)

    store.write_market_regime(
        symbol="NIFTY",
        ts=observed_at,
        trend_regime="BULL",
        volatility_regime="NORMAL",
        iv_regime="NORMAL",
        regime="BULL|NORMAL",
        features={"source": "legacy-context"},
    )
    store.write_daily_iv_regime(
        trade_date=date(2026, 10, 1),
        underlying="NIFTY",
        iv_level="HIGH_IV",
        iv_term_regime="CONTANGO",
        iv_skew_regime="NORMAL_SKEW",
        iv_regime="HIGH_IV_CONTANGO_NORMAL_SKEW",
        metrics={"atm_iv": 18.0},
    )

    context = store.get_market_regime_as_of("NIFTY", observed_at)
    iv = store.latest_daily_iv_regime(underlying="NIFTY", as_of=date(2026, 10, 1))
    vocabulary = store.conn.execute(
        "SELECT regime_vocabulary FROM market_regimes WHERE symbol='NIFTY'"
    ).fetchone()[0]

    assert context is not None
    assert context["regime"] == "BULL|NORMAL"
    assert vocabulary == "legacy_daily_v0"
    assert iv is not None
    assert iv["iv_regime"] == "HIGH_IV_CONTANGO_NORMAL_SKEW"
    assert iv["metrics"] == {"atm_iv": 18.0}
    store.close()


def test_canonical_policy_roundtrip_is_vocabulary_tagged(tmp_path):
    store = DuckDBStore(tmp_path / "canonical-policy.duckdb")
    policy = RegimePolicy(
        allowed_regimes=frozenset({CANONICAL}),
        regime_metrics={CANONICAL: {"trades": 120, "avg_pnl": 10.0}},
        selection_status="READY",
    )
    store.save_regime_policy(
        policy_id="policy-1",
        symbol="NIFTY",
        train_start=date(2026, 1, 1),
        train_end=date(2026, 6, 30),
        test_start=date(2026, 7, 1),
        test_end=date(2026, 12, 31),
        policy=policy,
        risk_limits={CANONICAL: {"allowed": True, "max_lots_per_order": 2}},
    )

    loaded = store.latest_regime_policy(
        "NIFTY", datetime(2026, 8, 1, tzinfo=UTC)
    )

    assert loaded is not None
    assert loaded["selection_status"] == "READY"
    assert loaded["regime_vocabulary"] == "canonical_v1"
    assert loaded["regime_metrics"][CANONICAL]["trades"] == 120
    store.close()


def test_noncanonical_policy_cannot_be_persisted_as_canonical(tmp_path):
    store = DuckDBStore(tmp_path / "reject-legacy-policy.duckdb")
    policy = RegimePolicy(
        allowed_regimes=frozenset({"BULL|NORMAL"}),
        regime_metrics={},
        selection_status="READY",
    )

    with pytest.raises(ValueError, match="non-canonical"):
        store.save_regime_policy(
            policy_id="legacy-policy",
            symbol="NIFTY",
            train_start=date(2026, 1, 1),
            train_end=date(2026, 6, 30),
            test_start=date(2026, 7, 1),
            test_end=date(2026, 12, 31),
            policy=policy,
        )
    store.close()
