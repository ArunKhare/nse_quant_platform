"""Idempotent migration adapter from legacy option_stream rows to Medallion Bronze.

This adapter preserves historical provider observations as immutable historical-import
artifacts. It does not claim live-provider provenance, decision eligibility, publication,
or production cutover.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.data_platform.native_option_chain_snapshot import (
    canonical,
    json_safe,
    sha,
)
from nse_quant.data_platform.native_option_chain_snapshot import (
    snapshot_id as compute_snapshot_id,
)
from nse_quant.data_platform.native_option_chain_snapshot_bronze import (
    preserve_option_chain_snapshot,
)

MIGRATION_COMMAND = "migrate.legacy_option_stream_to_bronze@1"
SOURCE_LABEL = "legacy_option_stream_historical_import"
ORIGIN_KIND = "historical_import"


@dataclass(frozen=True)
class OptionStreamSnapshot:
    underlying: str
    trading_date: date
    snapshot_ts: datetime
    rows: tuple[dict[str, Any], ...]

    @property
    def source_label(self) -> str:
        return SOURCE_LABEL

    def canonical_document(self) -> bytes:
        document = {
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
        return compute_snapshot_id(self.canonical_document())

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
    return preserve_option_chain_snapshot(
        bronze,
        source_label=snapshot.source_label,
        payload=payload,
        expected_snapshot_id=snapshot.snapshot_id,
        imported_at=snapshot.snapshot_ts,
        actor_id=actor_id,
        code_revision=code_revision,
        origin_kind=ORIGIN_KIND,
    )
