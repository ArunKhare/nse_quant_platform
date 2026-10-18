"""Export recent chain snapshots for deterministic replay."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nse_quant.core.models import ChainSnapshot, Instrument, OptionQuote, OptionType

logger = logging.getLogger(__name__)


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
            SELECT
                ts,
                spot,
                expiry,
                strike,
                option_type,
                tradingsymbol,
                instrument_token,
                lot_size,
                ltp,
                bid,
                ask,
                volume,
                oi,
                iv,
                delta,
                gamma,
                vega,
                theta
            FROM option_stream
            WHERE underlying = ?
              AND ts >= ?
            ORDER BY ts
            """,
            [underlying, cutoff],
        ).fetchall()

        grouped: dict[tuple[datetime, float, date], list[OptionQuote]] = {}
        for row in rows:
            (
                ts,
                spot,
                expiry,
                strike,
                option_type,
                tradingsymbol,
                instrument_token,
                lot_size,
                ltp,
                bid,
                ask,
                volume,
                oi,
                iv,
                delta,
                gamma,
                vega,
                theta,
            ) = row
            try:
                instrument = Instrument(
                    tradingsymbol=tradingsymbol,
                    instrument_token=instrument_token,
                    underlying=underlying,
                    expiry=expiry,
                    strike=strike,
                    option_type=OptionType(option_type),
                    lot_size=lot_size,
                )
                quote = OptionQuote(
                    instrument_token=instrument_token,
                    instrument=instrument,
                    ltp=ltp,
                    bid=bid,
                    ask=ask,
                    volume=volume,
                    oi=oi,
                    exchange_ts=ts,
                    iv=iv,
                    delta=delta,
                    gamma=gamma,
                    vega=vega,
                    theta=theta,
                )
            except (TypeError, ValueError, ValidationError) as exc:
                logger.warning(
                    "Skipping invalid replay quote at %s: %s",
                    ts,
                    exc,
                )
                continue
            grouped.setdefault((ts, spot, expiry), []).append(quote)

        snapshots = []
        for (ts, spot, expiry), quotes in grouped.items():
            snapshot = ChainSnapshot(
                underlying=underlying,
                ts=ts,
                spot=spot,
                expiry=expiry,
                quotes=quotes,
            )
            snapshots.append(snapshot.model_dump(mode="json"))
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