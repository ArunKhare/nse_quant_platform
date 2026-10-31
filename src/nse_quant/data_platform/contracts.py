"""Versioned dataset contracts for the medallion platform foundation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum


class Layer(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class WritePolicy(StrEnum):
    APPEND_OBSERVATIONS = "append_observations"
    APPEND_REVISIONS = "append_revisions"
    VERSIONED_BUILDS = "versioned_builds"


@dataclass(frozen=True)
class DatasetContract:
    name: str
    version: str
    layer: Layer
    write_policy: WritePolicy
    entity_keys: tuple[str, ...]
    required_columns: tuple[str, ...]
    owner: str

    def __post_init__(self) -> None:
        if not isinstance(self.layer, Layer) or not isinstance(self.write_policy, WritePolicy):
            raise TypeError("Use Layer and WritePolicy enum values")
        if not self.name.startswith(f"{self.layer.value}."):
            raise ValueError("Dataset name must start with its layer prefix")
        if not self.version.strip() or not self.owner.strip():
            raise ValueError("Version and owner are required")
        if not isinstance(self.entity_keys, tuple) or not isinstance(self.required_columns, tuple):
            raise TypeError("Keys and columns must be immutable tuples")
        if not self.entity_keys or not self.required_columns:
            raise ValueError("Keys and columns must not be empty")
        if any(not value.strip() for value in (*self.entity_keys, *self.required_columns)):
            raise ValueError("Keys and columns must not contain empty names")
        if len(set(self.entity_keys)) != len(self.entity_keys):
            raise ValueError("Duplicate entity keys")
        if len(set(self.required_columns)) != len(self.required_columns):
            raise ValueError("Duplicate required columns")
        if not set(self.entity_keys).issubset(self.required_columns):
            raise ValueError("Entity keys must be required columns")
        policies = {
            Layer.BRONZE: WritePolicy.APPEND_OBSERVATIONS,
            Layer.SILVER: WritePolicy.APPEND_REVISIONS,
            Layer.GOLD: WritePolicy.VERSIONED_BUILDS,
        }
        if self.write_policy != policies[self.layer]:
            raise ValueError("Write policy does not match the layer contract")
        if self.layer == Layer.BRONZE:
            required = {"received_at", "source", "payload_hash"}
        elif self.layer == Layer.SILVER:
            required = {"recorded_at", "source_observation_id", "revision_id"}
        else:
            required = {"build_id", "event_ts", "published_at", "feature_version"}
        if not required.issubset(self.required_columns):
            raise ValueError(f"Missing layer metadata: {sorted(required)}")

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
