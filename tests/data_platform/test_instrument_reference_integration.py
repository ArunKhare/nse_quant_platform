"""Real project A1/FS1a integration, supplied but not executed in reconstruction."""

import duckdb
import pytest

from nse_quant.data_platform.instrument_reference_service import (
    import_reference_artifact,
    lookup_reference,
    normalize_reference,
    object_name,
)

RAW = (
    b"instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,"
    b"tick_size,lot_size,instrument_type,segment,exchange\n"
    b"258,1,EXAMPLE,Provider name,123.4500,,0,0.05,1,EQ,NSE,NSE\n"
)


def test_offline_lineage_retry_and_lookup(tmp_path):
    b = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    s = duckdb.connect(str(tmp_path / "silver.duckdb"))
    try:
        args = dict(
            import_session_id="s",
            source_record_id="r",
            actor_id="test",
            code_revision="fixture",
            initialize=True,
        )
        event, envelope, conflict = import_reference_artifact(b, RAW, **args)
        assert not conflict
        assert import_reference_artifact(b, RAW, **args) == (event, envelope, False)
        options = dict(
            capture_event_id=event,
            envelope_hash=envelope,
            actor_id="test",
            code_revision="fixture",
            initialize=True,
        )
        revision = normalize_reference(b, s, **options)
        assert normalize_reference(b, s, **options) == revision
        table = object_name(s, "silver", "instrument_reference_snapshots")
        rows = s.execute(f"SELECT * FROM {table}").fetchall()
        assert len(rows) == 1 and rows[0][10:15] == (None, None, None, None, None)
        assert (
            lookup_reference(b, s, reference_revision_id=revision, instrument_token=258).status
            == "matched"
        )
    finally:
        s.close()
        b.close()


def test_changed_receipt_is_conflict_then_blocks_reuse(tmp_path):
    with duckdb.connect(str(tmp_path / "bronze.duckdb")) as b:
        args = dict(
            import_session_id="s",
            source_record_id="r",
            actor_id="test",
            code_revision="fixture",
            initialize=True,
        )
        event, envelope, _ = import_reference_artifact(b, RAW, **args)
        changed, variant, conflict = import_reference_artifact(
            b, RAW.replace(b"EXAMPLE", b"CHANGED"), **args
        )
        assert changed == event and variant != envelope and conflict
        with pytest.raises(ValueError, match="RECEIPT_CONFLICT_REQUIRES_REVIEW"):
            import_reference_artifact(b, RAW, **args)
