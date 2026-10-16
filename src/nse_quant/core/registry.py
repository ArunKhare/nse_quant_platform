"""Small service registry used by the decision loop and UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Registry(Generic[T]):
    _items: dict[str, T]

    def __init__(self) -> None:
        self._items = {}

    def register(self, name: str, item: T) -> None:
        if name in self._items:
            raise ValueError(f"Already registered: {name}")
        self._items[name] = item

    def get(self, name: str) -> T:
        return self._items[name]

    def all(self) -> dict[str, T]:
        return dict(self._items)


StrategyFactory = Callable[[], object]
