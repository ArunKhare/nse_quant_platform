"""Read-only persisted chain-snapshot provider for the decision loop."""

from __future__ import annotations

from nse_quant.core.models import ChainSnapshot
from nse_quant.persistence.duckdb_store import DuckDBStore


class PersistedChainSnapshotProvider:
    """Provide the latest complete persisted option-chain snapshots.

    This provider does not acquire live market data, write option-stream rows,
    authorize execution, or assert decision eligibility.
    """

    def __init__(
        self,
        store: DuckDBStore,
        *,
        underlying: str,
        required_expiries: int = 2,
    ) -> None:
        self.store = store
        self.underlying = underlying
        self.required_expiries = required_expiries

    def get_chain_snapshot(self) -> ChainSnapshot:
        snapshots = self.get_chain_snapshots()

        if not snapshots:
            raise ValueError("No complete persisted option-chain snapshots available")

        return snapshots[0]

    def get_chain_snapshots(self) -> list[ChainSnapshot]:
        return self.store.latest_complete_chain_snapshots(
            self.underlying,
            required_expiries=self.required_expiries,
        )
