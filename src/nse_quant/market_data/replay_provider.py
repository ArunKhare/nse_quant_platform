import json
from pathlib import Path

from nse_quant.core.models import ChainSnapshot


class ReplayExhaustedError(StopIteration):
    """Raised when a replay has no further snapshots."""


class ReplayMarketDataProvider:
    def __init__(
        self,
        snapshots: list[ChainSnapshot],
        *,
        spot_instrument_tokens: dict[str, int] | None = None,
    ) -> None:
        if not snapshots:
            raise ValueError("ReplayMarketDataProvider requires snapshots")

        self._snapshots = snapshots
        self._index = 0
        self._spot_instrument_tokens = spot_instrument_tokens or {}

    def get_chain_snapshot(self) -> ChainSnapshot:
        if self._index >= len(self._snapshots):
            raise ReplayExhaustedError("Replay snapshots exhausted")

        snapshot = self._snapshots[self._index]
        self._index += 1
        return snapshot

    def resolve_spot_instrument_token(
        self,
        symbol: str,
    ) -> int:
        token = self._spot_instrument_tokens.get(symbol)

        if token is None:
            raise ValueError(f"No spot instrument token configured for replay symbol '{symbol}'")

        return token

    @property
    def remaining(self) -> int:
        return max(0, len(self._snapshots) - self._index)

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        *,
        spot_instrument_tokens: dict[str, int] | None = None,
    ) -> "ReplayMarketDataProvider":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))

        snapshots = [ChainSnapshot.model_validate(item) for item in payload["snapshots"]]

        underlying = payload.get("underlying")
        embedded_token = payload.get("spot_instrument_token")

        tokens = dict(spot_instrument_tokens or {})

        if underlying and embedded_token is not None:
            tokens.setdefault(underlying, int(embedded_token))

        return cls(
            snapshots,
            spot_instrument_tokens=tokens,
        )
