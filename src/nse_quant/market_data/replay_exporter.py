"""Export recent chain snapshots for deterministic replay."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nse_quant.core.models import (
    ChainSnapshot,
    Instrument,
    OptionQuote,
    OptionType,
)
from nse_quant.core.settings import get_settings

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
        """Export snapshots from the trailing N-minute window."""
        if minutes <= 0:
            raise ValueError("minutes must be positive")

        cutoff = datetime.now(UTC).astimezone() - timedelta(minutes=minutes)
        cutoff = cutoff.replace(tzinfo=None)

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

        logger.info(
            "Replay export selected %d option rows for %s since %s",
            len(rows),
            underlying,
            cutoff,
        )

        return self._write_replay(
            underlying=underlying,
            rows=rows,
            output_path=output_path,
        )

    def export_snapshots(
        self,
        *,
        underlying: str,
        output_path: str | Path,
        from_dt: datetime,
        to_dt: datetime,
    ) -> Path:
        if to_dt <= from_dt:
            raise ValueError("to_dt must be later than from_dt")

        # The option_stream table stores naive local/IST timestamps.
        # Convert timezone-aware CLI inputs to the same representation.
        if from_dt.tzinfo is not None:
            from_dt = from_dt.astimezone().replace(tzinfo=None)

        if to_dt.tzinfo is not None:
            to_dt = to_dt.astimezone().replace(tzinfo=None)

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
              AND ts <= ?
            ORDER BY ts
            """,
            [underlying, from_dt, to_dt],
        ).fetchall()

        logger.info(
            "Replay range export selected %d rows for %s between %s and %s",
            len(rows),
            underlying,
            from_dt,
            to_dt,
        )
        print(f"DEBUG range: {len(rows)} rows, from={from_dt!r}, to={to_dt!r}")
        if rows:
            print("DEBUG first:", rows[0])

        return self._write_replay(
            underlying=underlying,
            rows=rows,
            output_path=output_path,
        )

    def _write_replay(
        self, *, underlying: str, rows: list[tuple[Any, ...]], output_path: str | Path
    ) -> Path:
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
            print(snapshot)
            snapshots.append(snapshot.model_dump(mode="json"))
        if not snapshots:
            raise ValueError("No replayable snapshots could be reconstructed")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "underlying": underlying,
                    "spot_instrument_token": self._resolve_spot_token(underlying),
                    "snapshots": snapshots,
                },
                default=str,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return output

    # def _resolve_spot_token(self, underlying: str) -> int | None:
    #     row = self.store.conn.execute(
    #         """
    #         SELECT instrument_token
    #         FROM spot_instruments
    #         WHERE symbol = ?
    #         LIMIT 1
    #         """,
    #         [underlying],
    #     ).fetchone()

    #     return row[0] if row else None

    def _resolve_spot_token(self, underlying: str) -> int | None:
        settings = get_settings()
        return settings.market_data.index_instrument_tokens.get(underlying)
