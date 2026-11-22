from pathlib import Path

from nse_quant.persistence.store_factory import (
    open_decisions_store,
    open_market_data_store,
    open_paper_orders_store,
)
from nse_quant.persistence.store_paths import (
    OperationalStore,
    decisions_store_path,
    market_data_store_path,
    operational_store_path,
    paper_orders_store_path,
)


def test_store_paths_are_separate(tmp_path: Path) -> None:
    base = tmp_path / "legacy.duckdb"

    market = market_data_store_path(base_path=base)
    decisions = decisions_store_path(base_path=base)
    orders = paper_orders_store_path(base_path=base)

    assert market != decisions
    assert decisions != orders
    assert market != orders

    assert market.parent == base.parent / "operational"
    assert market.name == "market_data.duckdb"
    assert decisions.name == "decisions.duckdb"
    assert orders.name == "paper_orders.duckdb"


def test_named_store_path_resolution(tmp_path: Path) -> None:
    base = tmp_path / "legacy.duckdb"

    assert operational_store_path(OperationalStore.MARKET_DATA, base_path=base) == (
        base.parent / "operational" / "market_data.duckdb"
    )


def test_store_factory_creates_separate_databases(tmp_path: Path) -> None:
    base = tmp_path / "legacy.duckdb"

    market = open_market_data_store(base_path=base)
    decisions = open_decisions_store(base_path=base)
    orders = open_paper_orders_store(base_path=base)

    try:
        assert market.path != decisions.path
        assert decisions.path != orders.path
        assert market.path.exists()
        assert decisions.path.exists()
        assert orders.path.exists()
    finally:
        market.close()
        decisions.close()
        orders.close()


def test_read_only_market_store_factory(tmp_path: Path) -> None:
    base = tmp_path / "legacy.duckdb"

    writer = open_market_data_store(base_path=base)
    try:
        pass
    finally:
        writer.close()

    reader = open_market_data_store(read_only=True, base_path=base)
    try:
        assert reader.conn is not None
    finally:
        reader.close()
