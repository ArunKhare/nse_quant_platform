"""Actual market Gold bundle -> persisted decision-evidence chain."""

from datetime import UTC, date, datetime

import duckdb
import pandas as pd
import pytest

from nse_quant.data_platform import (
    legacy_daily_rv_gold as rv_gold,
)
from nse_quant.data_platform import (
    legacy_daily_rv_observations_bronze as rv_bronze,
)
from nse_quant.data_platform import (
    legacy_daily_rv_observations_silver as rv_silver,
)
from nse_quant.data_platform import (
    legacy_decision_evidence as evidence,
)
from nse_quant.data_platform import (
    legacy_market_gold_bundle as bundle,
)
from nse_quant.data_platform import (
    legacy_market_regimes_bronze as regime_bronze,
)
from nse_quant.data_platform import (
    legacy_market_regimes_gold as regime_gold,
)
from nse_quant.data_platform import (
    legacy_market_regimes_silver as regime_silver,
)
from nse_quant.data_platform import (
    legacy_silver_common as base,
)
from nse_quant.data_platform import (
    legacy_spot_candles_bronze as candle_bronze,
)
from nse_quant.data_platform import (
    legacy_spot_candles_gold as candle_gold,
)
from nse_quant.data_platform import (
    legacy_spot_candles_silver as candle_silver,
)
from nse_quant.data_platform import (
    legacy_spot_features_bronze as feature_bronze,
)
from nse_quant.data_platform import (
    legacy_spot_features_gold as feature_gold,
)
from nse_quant.data_platform import (
    legacy_spot_features_silver as feature_silver,
)
from nse_quant.data_platform import (
    legacy_underlying_iv_gold as iv_gold,
)
from nse_quant.data_platform import (
    legacy_underlying_iv_observations_bronze as iv_bronze,
)
from nse_quant.data_platform import (
    legacy_underlying_iv_observations_silver as iv_silver,
)
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
DAY = date(2026, 1, 1)
EXPIRY = date(2026, 1, 29)
REVISION = "a" * 40


def build_chain(tmp_path):
    def bronze(name, capture, preserve, seeder):
        legacy_path, bronze_path = (
            tmp_path / f"{name}_legacy.duckdb",
            tmp_path / f"{name}_bronze.duckdb",
        )
        seeder(legacy_path)
        with (
            duckdb.connect(str(legacy_path), read_only=True) as source,
            duckdb.connect(str(bronze_path)) as target,
        ):
            AuditLedger(target).initialize()
            BronzeEventStore(target).initialize()
            snapshot = capture(source, source_label="fixture")
            result = preserve(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        return bronze_path, base.SilverPins(
            result["source_label"],
            result["snapshot_id"],
            result["capture_event_id"],
            result["envelope_hash"],
            result["recording_fingerprint"],
        )

    def silver(name, bronze_path, pins, init, observe, persist):
        silver_path = tmp_path / f"{name}_silver.duckdb"
        with (
            duckdb.connect(str(bronze_path), read_only=True) as bronze_conn,
            duckdb.connect(str(silver_path)) as target,
        ):
            init(target)
            context = observe(bronze_conn, pins=pins)
            receipt = persist(
                bronze_conn,
                target,
                pins=pins,
                expected_context_sha256=base.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        return silver_path, receipt

    def gold(name, silver_path, pins, silver_receipt, init, observe, persist):
        gold_path = tmp_path / f"{name}_gold.duckdb"
        with (
            duckdb.connect(str(silver_path), read_only=True) as silver_reader,
            duckdb.connect(str(gold_path)) as target,
        ):
            init(target)
            context = observe(
                silver_reader,
                pins=pins,
                revision_id=silver_receipt["revision_id"],
                expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
            )
            receipt = persist(
                silver_reader,
                target,
                pins=pins,
                silver_revision_id=silver_receipt["revision_id"],
                expected_silver_recording_fingerprint=silver_receipt["recording_fingerprint"],
                expected_context_sha256=base.sha(context),
                actor_id="synthetic",
                code_revision=REVISION,
            )
        return gold_path, receipt

    def seed_candles(p):
        store = DuckDBStore(path=p)
        try:
            store.write_spot_candles(
                [
                    dict(
                        date=AT,
                        open=100.0,
                        high=110.0,
                        low=95.0,
                        close=105.0,
                        volume=1000,
                    )
                ],
                "NIFTY",
                12345,
                "minute",
            )
        finally:
            store.close()

    def seed_features(p):
        store = DuckDBStore(path=p)
        try:
            store.write_spot_features(
                pd.DataFrame(
                    [
                        dict(
                            symbol="NIFTY",
                            ts=AT,
                            close=100.5,
                            return_1m=0.001,
                            rv_1m_30=0.12,
                            atr_1m_14=1.25,
                            vwap_1m=100.25,
                            vwap_distance_1m=0.0025,
                            volume_zscore_1m_30=0.75,
                            trend_15m=0.5,
                            atr_15m_14=2.5,
                            range_position_15m=0.65,
                            trend_60m=0.4,
                            atr_60m_14=3.5,
                            range_position_60m=0.55,
                        )
                    ]
                )
            )
        finally:
            store.close()

    def seed_regimes(p):
        store = DuckDBStore(path=p)
        try:
            store.write_market_regime(
                symbol="NIFTY",
                ts=AT,
                trend_regime="TREND_UP",
                volatility_regime="NORMAL",
                iv_regime="HIGH",
                regime="TREND_UP",
                features={"atm_iv": 0.15},
            )
        finally:
            store.close()

    def seed_iv(p):
        store = DuckDBStore(path=p)
        try:
            table = iv_bronze.common.name(store.conn, "main", iv_bronze.codec.TABLE)
            store.conn.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?)",
                [AT, "NIFTY", EXPIRY, 0.15, 24500.5, "atm_average_live"],
            )
        finally:
            store.close()

    def seed_rv(p):
        store = DuckDBStore(path=p)
        try:
            table = rv_bronze.common.name(store.conn, "main", rv_bronze.codec.TABLE)
            store.conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)", ["NIFTY", DAY, 0.12, 375])
        finally:
            store.close()

    candle_bronze_path, pins = bronze(
        "candles",
        candle_bronze.capture_spot_candles,
        candle_bronze.preserve_spot_candles,
        seed_candles,
    )
    candle_silver_path, candle_silver_receipt = silver(
        "candles",
        candle_bronze_path,
        pins,
        candle_silver.initialize_spot_candles_silver,
        candle_silver.observe_spot_candles_bronze,
        candle_silver.persist_spot_candles_silver,
    )
    candle_gold_path, candle_gold_receipt = gold(
        "candles",
        candle_silver_path,
        pins,
        candle_silver_receipt,
        candle_gold.initialize_spot_candles_gold,
        candle_gold.observe_spot_candles_silver,
        candle_gold.persist_spot_candles_gold,
    )

    feature_bronze_path, feature_pins = bronze(
        "features",
        feature_bronze.capture_spot_features,
        feature_bronze.preserve_spot_features,
        seed_features,
    )
    feature_silver_path, feature_silver_receipt = silver(
        "features",
        feature_bronze_path,
        feature_pins,
        feature_silver.initialize_spot_features_silver,
        feature_silver.observe_spot_features_bronze,
        feature_silver.persist_spot_features_silver,
    )
    feature_gold_path, feature_gold_receipt = gold(
        "features",
        feature_silver_path,
        feature_pins,
        feature_silver_receipt,
        feature_gold.initialize_spot_features_gold,
        feature_gold.observe_spot_features_silver,
        feature_gold.persist_spot_features_gold,
    )

    regime_bronze_path, regime_pins = bronze(
        "regimes",
        regime_bronze.capture_market_regimes,
        regime_bronze.preserve_market_regimes,
        seed_regimes,
    )
    regime_silver_path, regime_silver_receipt = silver(
        "regimes",
        regime_bronze_path,
        regime_pins,
        regime_silver.initialize_market_regimes_silver,
        regime_silver.observe_market_regimes_bronze,
        regime_silver.persist_market_regimes_silver,
    )
    regime_gold_path, regime_gold_receipt = gold(
        "regimes",
        regime_silver_path,
        regime_pins,
        regime_silver_receipt,
        regime_gold.initialize_market_regimes_gold,
        regime_gold.observe_market_regimes_silver,
        regime_gold.persist_market_regimes_gold,
    )

    iv_bronze_path, iv_pins = bronze(
        "iv",
        iv_bronze.capture_underlying_iv_observations,
        iv_bronze.preserve_underlying_iv_observations,
        seed_iv,
    )
    iv_silver_path, iv_silver_receipt = silver(
        "iv",
        iv_bronze_path,
        iv_pins,
        iv_silver.initialize_underlying_iv_observations_silver,
        iv_silver.observe_underlying_iv_observations_bronze,
        iv_silver.persist_underlying_iv_observations_silver,
    )
    iv_gold_path, iv_gold_receipt = gold(
        "iv",
        iv_silver_path,
        iv_pins,
        iv_silver_receipt,
        iv_gold.initialize_underlying_iv_gold,
        iv_gold.observe_underlying_iv_silver,
        iv_gold.persist_underlying_iv_gold,
    )

    rv_bronze_path, rv_pins = bronze(
        "rv",
        rv_bronze.capture_daily_rv_observations,
        rv_bronze.preserve_daily_rv_observations,
        seed_rv,
    )
    rv_silver_path, rv_silver_receipt = silver(
        "rv",
        rv_bronze_path,
        rv_pins,
        rv_silver.initialize_daily_rv_silver,
        rv_silver.observe_daily_rv_bronze,
        rv_silver.persist_daily_rv_silver,
    )
    rv_gold_path, rv_gold_receipt = gold(
        "rv",
        rv_silver_path,
        rv_pins,
        rv_silver_receipt,
        rv_gold.initialize_daily_rv_gold,
        rv_gold.observe_daily_rv_silver,
        rv_gold.persist_daily_rv_gold,
    )

    revision_ids = {
        "spot_candles": candle_gold_receipt["revision_id"],
        "spot_features": feature_gold_receipt["revision_id"],
        "market_regimes": regime_gold_receipt["revision_id"],
        "underlying_iv": iv_gold_receipt["revision_id"],
        "daily_rv": rv_gold_receipt["revision_id"],
    }
    gold_recording_fingerprints = {
        "spot_candles": candle_gold_receipt["recording_fingerprint"],
        "spot_features": feature_gold_receipt["recording_fingerprint"],
        "market_regimes": regime_gold_receipt["recording_fingerprint"],
        "underlying_iv": iv_gold_receipt["recording_fingerprint"],
        "daily_rv": rv_gold_receipt["recording_fingerprint"],
    }
    gold_paths = {
        "spot_candles": candle_gold_path,
        "spot_features": feature_gold_path,
        "market_regimes": regime_gold_path,
        "underlying_iv": iv_gold_path,
        "daily_rv": rv_gold_path,
    }
    bundle_path = tmp_path / "bundle_gold.duckdb"
    readers = {name: duckdb.connect(str(path), read_only=True) for name, path in gold_paths.items()}
    target = duckdb.connect(str(bundle_path))
    try:
        bundle.initialize_market_gold_bundle(target)
        context = bundle.observe_market_gold_bundle(
            readers,
            pins=pins,
            revision_ids=revision_ids,
            gold_recording_fingerprints=gold_recording_fingerprints,
        )
        bundle_receipt = bundle.persist_market_gold_bundle(
            readers,
            target,
            pins=pins,
            revision_ids=revision_ids,
            gold_recording_fingerprints=gold_recording_fingerprints,
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        for reader in readers.values():
            reader.close()
        target.close()

    evidence_pins = base.SilverPins(
        source_label=pins.source_label,
        snapshot_id=pins.snapshot_id,
        capture_event_id=pins.capture_event_id,
        envelope_hash=pins.envelope_hash,
        recording_fingerprint=bundle_receipt["recording_fingerprint"],
    )
    evidence_path = tmp_path / "evidence_gold.duckdb"
    bundle_reader = duckdb.connect(str(bundle_path), read_only=True)
    evidence_target = duckdb.connect(str(evidence_path))
    try:
        evidence.initialize_decision_evidence(evidence_target)
        context = evidence.observe_decision_evidence_bundle(
            bundle_reader,
            pins=evidence_pins,
            bundle_revision_id=bundle_receipt["revision_id"],
        )
        evidence_receipt = evidence.persist_decision_evidence(
            bundle_reader,
            evidence_target,
            pins=evidence_pins,
            bundle_revision_id=bundle_receipt["revision_id"],
            expected_context_sha256=base.sha(context),
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        bundle_reader.close()
        evidence_target.close()
    return bundle_path, evidence_path, evidence_pins, bundle_receipt, evidence_receipt


def test_decision_evidence_chain(tmp_path):
    bundle_path, evidence_path, pins, bundle_receipt, evidence_receipt = build_chain(tmp_path)
    bundle_reader = duckdb.connect(str(bundle_path), read_only=True)
    evidence_reader = duckdb.connect(str(evidence_path), read_only=True)
    try:
        records = evidence.read_decision_evidence(
            evidence_reader,
            revision_id=evidence_receipt["revision_id"],
            expected_recording_fingerprint=evidence_receipt["recording_fingerprint"],
        )
        assert set(records) == set(evidence.MEMBERS)
        assert sum(len(value) for value in records.values()) == evidence_receipt["row_count"] == 5
        assert records == bundle.read_market_gold_bundle(
            bundle_reader,
            revision_id=bundle_receipt["revision_id"],
            expected_recording_fingerprint=bundle_receipt["recording_fingerprint"],
        )
        assert records == evidence.revalidate_decision_evidence(
            bundle_reader,
            evidence_reader,
            revision_id=evidence_receipt["revision_id"],
            expected_recording_fingerprint=evidence_receipt["recording_fingerprint"],
            source_label=pins.source_label,
            snapshot_id=pins.snapshot_id,
            capture_event_id=pins.capture_event_id,
            envelope_hash=pins.envelope_hash,
            bundle_revision_id=bundle_receipt["revision_id"],
            bundle_recording_fingerprint=pins.recording_fingerprint,
        )
    finally:
        bundle_reader.close()
        evidence_reader.close()


def test_evidence_first_write_original_obligation(tmp_path):
    bundle_path, evidence_path, pins, bundle_receipt, _er = build_chain(tmp_path)
    bundle_reader = duckdb.connect(str(bundle_path), read_only=True)
    target = duckdb.connect(str(evidence_path))
    try:
        context = evidence.observe_decision_evidence_bundle(
            bundle_reader, pins=pins, bundle_revision_id=bundle_receipt["revision_id"]
        )
        with pytest.raises(ValueError, match="FIRST_WRITE"):
            evidence.persist_decision_evidence(
                bundle_reader,
                target,
                pins=pins,
                bundle_revision_id=bundle_receipt["revision_id"],
                expected_context_sha256=base.sha(context),
                actor_id="other",
                code_revision="b" * 40,
            )
    finally:
        bundle_reader.close()
        target.close()


def test_evidence_same_file_alias_separate_target(tmp_path):
    bundle_path, evidence_path, pins, bundle_receipt, _er = build_chain(tmp_path)
    bundle_reader = duckdb.connect(str(bundle_path), read_only=True)
    target = duckdb.connect(str(evidence_path))
    alias = target.cursor()
    try:
        with pytest.raises(ValueError, match="SEPARATE"):
            evidence.persist_decision_evidence(
                alias,
                target,
                pins=pins,
                bundle_revision_id=bundle_receipt["revision_id"],
                expected_context_sha256="a" * 64,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert target.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        bundle_reader.close()
        target.close()


def test_evidence_tampering_blocks_read(tmp_path):
    bundle_path, evidence_path, pins, bundle_receipt, evidence_receipt = build_chain(tmp_path)
    with duckdb.connect(str(evidence_path)) as writer:
        writer.execute("UPDATE gold.decision_evidence_sets SET context='bad'::BLOB")
    with duckdb.connect(str(evidence_path), read_only=True) as reader, pytest.raises(ValueError):
        evidence.read_decision_evidence(
            reader,
            revision_id=evidence_receipt["revision_id"],
            expected_recording_fingerprint=evidence_receipt["recording_fingerprint"],
        )
