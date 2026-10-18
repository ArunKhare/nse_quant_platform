"""Export recent chain snapshots for deterministic replay."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nse_quant.core.models import ChainSnapshot


class ReplayExporter:
    def __init__(self, store: Any) -> None:
        self.store = store

    def export_recent_snapshots(
        self,
        underlying: str,
        output_path: str | Path,
        minutes: int = 30,
    ) -> Path:
        cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

        rows = self.store.conn.execute(
            """
            SELECT ts, payload_json
            FROM option_stream
            WHERE underlying = ?
              AND ts >= ?
            ORDER BY ts
            """,
            [underlying, cutoff],
        ).fetchall()

        grouped: dict[object, list[str]] ={}

        for ts, payload_json in rows:
            grouped.setdefault(ts,[]).append(payload_json)

        snapshot = []
        for ts, payload_jsons in grouped.items():
            try:
                quotes = [
                    OptionQuote.model_validate_json(payload)
                    for payload in payloads
                ]

                first = quotes[0].instrument
                snapshot = ChainSnapshot(
                    underlying=underlying,
                    ts=ts,
                    spot=quotes[0].instrument.underlying_spot
                    if hasattr(quotes[0].instrument, "underlying_spot")
                    else None,
                    expiry=first.expiry,
                    quotes=quotes,
                )

                snapshots.append(snapshot.model_dump(mode="json"))
            except Exception:
                continue
        if not snapshots:
            raise ValueError("No replayable snapshots could be reconstructed")


        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        output.write_text(
            json.dumps(
                {"underlying": underlying, "snapshots": snapshots},
                default=str,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

        return output