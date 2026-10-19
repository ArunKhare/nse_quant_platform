import json
from pathlib import Path

from nse_quant.core.models import ChainSnapshot


class ReplayExhaustedError(StopIteration):
    """Raised when a replay has no further snapshots."""


class ReplayMarketDataProvider:
    def __init__(
        self,
        snapshots: list[ChainSnapshot],
    ) -> None:
        if not snapshots:
            raise ValueError(
                "ReplayMarketDataProvider requires snapshots"
            )

        self._snapshots = snapshots
        self._index = 0

    @classmethod
    def from_json(
        cls,
        path: str | Path,
    ) -> "ReplayMarketDataProvider":
        payload = json.loads(
            Path(path).read_text(encoding="utf-8")
        )

        snapshots = [
            ChainSnapshot.model_validate(item)
            for item in payload["snapshots"]
        ]

        return cls(snapshots)

    def get_chain_snapshot(self) -> ChainSnapshot:
        if self._index >= len(self._snapshots):
            raise ReplayExhaustedError(
                "Replay snapshots exhausted"
            )

        snapshot = self._snapshots[self._index]
        self._index += 1
        return snapshot

    @property
    def remaining(self) -> int:
        return max(0, len(self._snapshots) - self._index)