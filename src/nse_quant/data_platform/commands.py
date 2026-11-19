"""Explicit command definitions and bindings; no automatic legacy-script execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from nse_quant.data_platform.scopes import ExecutionScope


class Category(StrEnum):
    INGEST = "ingest"
    NORMALIZE = "normalize"
    BUILD = "build"
    EXPORT = "export"
    INSPECT = "inspect"
    WORKFLOW = "workflow"


@dataclass(frozen=True)
class CommandDefinition:
    name: str
    version: str
    category: Category
    owner: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.name, self.version, self.owner)):
            raise ValueError("Command name, version and owner are required")
        if not isinstance(self.category, Category):
            raise TypeError("Use a Category enum")
        for datasets in (self.reads, self.writes):
            if not isinstance(datasets, tuple):
                raise TypeError("Dataset lists must be immutable tuples")
            if len(set(datasets)) != len(datasets):
                raise ValueError("Duplicate datasets")
            for dataset in datasets:
                parts = dataset.split(".")
                if len(parts) != 2 or parts[0] not in {"bronze", "silver", "gold"}:
                    raise ValueError("Use a bronze/silver/gold dataset name")
                if not parts[1].isidentifier():
                    raise ValueError("Invalid dataset identifier")
        if self.category == Category.WORKFLOW:
            if self.reads or self.writes:
                raise ValueError("Workflows must delegate domain I/O to registered children")
            return
        if self.category in {Category.EXPORT, Category.INSPECT}:
            if self.writes or not self.reads:
                raise ValueError("Export/inspect commands read datasets without domain writes")
            return
        output_layer = {
            Category.INGEST: "bronze",
            Category.NORMALIZE: "silver",
            Category.BUILD: "gold",
        }[self.category]
        if not self.writes or any(not item.startswith(output_layer + ".") for item in self.writes):
            raise ValueError("Command writes outside its permitted layer")
        allowed_inputs = {
            Category.INGEST: set(),
            Category.NORMALIZE: {"bronze"},
            Category.BUILD: {"silver", "gold"},
        }[self.category]
        if any(item.split(".")[0] not in allowed_inputs for item in self.reads):
            raise ValueError("Command reads outside its declared layer boundary")
        if self.category != Category.INGEST and not self.reads:
            raise ValueError("Normalize/build commands must declare inputs")


@dataclass(frozen=True)
class CommandResult:
    rows_read: int = 0
    rows_written: int = 0
    rows_rejected: int = 0
    output_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for count in (self.rows_read, self.rows_written, self.rows_rejected):
            if type(count) is not int or count < 0:
                raise ValueError("Counts must be nonnegative integers")
        if not isinstance(self.output_refs, tuple):
            raise TypeError("Output references must be an immutable tuple")
        if any(not ref.strip() for ref in self.output_refs):
            raise ValueError("Output references must be nonempty identifiers")


Executor = Callable[[ExecutionScope], CommandResult]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[tuple[str, str], tuple[CommandDefinition, Executor]] = {}

    def register(self, definition: CommandDefinition, executor: Executor) -> bool:
        key = (definition.name, definition.version)
        if key in self._commands:
            current, bound = self._commands[key]
            if current != definition or bound is not executor:
                raise ValueError("Command version already has another definition or executor")
            return False
        self._commands[key] = (definition, executor)
        return True

    def resolve(self, name: str, version: str) -> tuple[CommandDefinition, Executor]:
        try:
            return self._commands[(name, version)]
        except KeyError:
            raise ValueError("Unregistered command/version") from None
