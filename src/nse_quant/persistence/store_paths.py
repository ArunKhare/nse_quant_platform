"""Operational DuckDB store-path ownership contract.

The platform separates independent write domains so that kite_stream and
paper_loop can run concurrently in separate terminals.

- market_data.duckdb: written by kite_stream
- decisions.duckdb: written by paper_loop
- paper_orders.duckdb: written by paper_loop

Readers must open a store they do not own in read-only mode.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from nse_quant.core.settings import get_settings


class OperationalStore(StrEnum):
    """Named operational DuckDB stores."""

    MARKET_DATA = "market_data"
    DECISIONS = "decisions"
    PAPER_ORDERS = "paper_orders"


def operational_store_path(store: OperationalStore, *, base_path: Path | None = None) -> Path:
    """Resolve the path for a named operational DuckDB store.

    The legacy configured database remains the compatibility fallback for
    existing callers until each process is migrated to its owned store.
    """
    settings = get_settings()
    configured_path = Path(base_path or settings.storage.db_path)
    operational_dir = configured_path.parent / "operational"
    return operational_dir / f"{store.value}.duckdb"


def market_data_store_path(*, base_path: Path | None = None) -> Path:
    return operational_store_path(OperationalStore.MARKET_DATA, base_path=base_path)


def decisions_store_path(*, base_path: Path | None = None) -> Path:
    return operational_store_path(OperationalStore.DECISIONS, base_path=base_path)


def paper_orders_store_path(*, base_path: Path | None = None) -> Path:
    return operational_store_path(OperationalStore.PAPER_ORDERS, base_path=base_path)
