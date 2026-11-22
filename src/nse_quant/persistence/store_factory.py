"""Factory for process-owned DuckDB stores.

Use this factory instead of constructing DuckDBStore directly in entry-point
scripts. It makes the writer/reader ownership boundary explicit.

Rules:
- kite_stream owns MARKET_DATA.
- paper_loop owns DECISIONS and PAPER_ORDERS.
- Readers of a store they do not own must use read_only=True.
"""

from __future__ import annotations

from pathlib import Path

from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.persistence.store_paths import (
    OperationalStore,
    decisions_store_path,
    market_data_store_path,
    operational_store_path,
    paper_orders_store_path,
)


def open_market_data_store(*, read_only: bool = False, base_path: Path | None = None) -> DuckDBStore:
    """Open the market-data store.

    kite_stream is the sole writer. paper_loop, dashboard, research, and tests
    must open this store with read_only=True.
    """
    return DuckDBStore(
        path=market_data_store_path(base_path=base_path),
        read_only=read_only,
    )


def open_decisions_store(*, read_only: bool = False, base_path: Path | None = None) -> DuckDBStore:
    """Open the decision-store owned by paper_loop."""
    return DuckDBStore(
        path=decisions_store_path(base_path=base_path),
        read_only=read_only,
    )


def open_paper_orders_store(*, read_only: bool = False, base_path: Path | None = None) -> DuckDBStore:
    """Open the paper-order store owned by paper_loop."""
    return DuckDBStore(
        path=paper_orders_store_path(base_path=base_path),
        read_only=read_only,
    )


def open_operational_store(
    store: OperationalStore,
    *,
    read_only: bool = False,
    base_path: Path | None = None,
) -> DuckDBStore:
    """Open a named operational store using the canonical ownership contract."""
    return DuckDBStore(
        path=operational_store_path(store, base_path=base_path),
        read_only=read_only,
    )
