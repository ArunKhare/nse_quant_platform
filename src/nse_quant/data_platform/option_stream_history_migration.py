"""Idempotent migration adapter from legacy option_stream rows to Medallion Bronze.

This adapter preserves historical provider observations as immutable historical-import
artifacts. It does not claim live-provider provenance, decision eligibility, publication,
or production cutover.

Legacy option-stream rows are preserved in their own legacy artifact format rather than
being reshaped into the native option-chain snapshot codec.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.native_option_chain_snapshot import (
    canonical,
    json_safe,
    sha,
)

MIGRATION_COMMAND = "migrate.legacy_option_stream_to_bronze@1"
SOURCE_LABEL_PREFIX = "legacy_option_stream_historical_import"
PAYLOAD_FORMAT = "legacy-option-stream-snapshot@1"
ORIGIN_KIND = "historical_import"


@dataclass(frozen=True)
class OptionStreamSnapshot:
    underlying: str
    trading_date: date
    snapshot_ts: datetime
    rows: tuple[dict[str, Any], ...]

    @property
    def content_hash(self) -> str:
        return sha(
            canonical(
                [
                    self.underlying,
                    self.trading_date.isoformat(),
                    self.snapshot_ts.isoformat(),
                    list(self.rows),
                ]
            )
        )

    @property
    def source_label(self) -> str:
        return f"{SOURCE_LABEL_PREFIX}:{self.content_hash}"

    def canonical_document(self) -> bytes:
        document = {
            "artifact_format": PAYLOAD_FORMAT,
            "source_label": self.source_label,
            "snapshot": {
                "underlying": self.underlying,
                "trading_date": self.trading_date.isoformat(),
                "snapshot_ts": self.snapshot_ts.isoformat(),
                "rows": list(self.rows),
            },
        }
        return canonical(json_safe(document))

    @property
    def snapshot_id(self) -> str:
        return sha(self.canonical_document())

    @property
    def batch_key(self) -> str:
        return sha(canonical([MIGRATION_COMMAND, self.source_label, self.snapshot_id]))


def migrate_option_stream_snapshot(
    bronze: Any,
    snapshot: OptionStreamSnapshot,
    *,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Preserve one legacy option-stream snapshot as an immutable Bronze artifact."""
    payload = snapshot.canonical_document()
    store = BronzeEventStore(bronze)
    store.verify_target()
    ledger = AuditLedger(bronze)
    job_id = ledger.plan_job(
        command_name=MIGRATION_COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + snapshot.content_hash,
        code_revision=code_revision,
        config_hash=sha(canonical([PAYLOAD_FORMAT, snapshot.snapshot_id])),
    )
    event = BronzeEvent(
        source=SOURCE_LABEL_PREFIX,
        capture_session_id=snapshot.source_label,
        source_record_id=snapshot.snapshot_id,
        received_at=snapshot.snapshot_ts,
        payload=payload,
        payload_format=PAYLOAD_FORMAT,
        origin_kind=ORIGIN_KIND,
    )
    with ledger.execution(job_id):
        receipt = store.append_batch(
            (event,),
            batch_key=snapshot.batch_key,
            input_artifact=payload,
            job_id=job_id,
        )
        if receipt.inserted_variants != 1:
            raise ValueError("Legacy snapshot was not inserted exactly once")
    return {
        "source_label": snapshot.source_label,
        "snapshot_id": snapshot.snapshot_id,
        "capture_event_id": event.capture_event_id,
        "envelope_hash": event.envelope_hash,
        "recording_fingerprint": receipt.batch_fingerprint,
        "row_count": len(snapshot.rows),
        "job_id": job_id,
        "decision_eligibility_asserted": False,
    }
