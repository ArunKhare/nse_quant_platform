"""Capture-quality checks for live option-stream snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass
class CaptureQualityResult:
    is_usable: bool
    issues: list[str] = field(
        default_factory=list
    )
    warnings: list[str] = field(
        default_factory=list
    )
    row_count: int = 0
    expiry_count: int = 0
    missing_ltp: int = 0
    missing_delta: int = 0
    bad_ltp: int = 0
    duplicate_contracts: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "is_usable": self.is_usable,
            "issues": self.issues,
            "warnings": self.warnings,
            "row_count": self.row_count,
            "expiry_count": self.expiry_count,
            "missing_ltp": self.missing_ltp,
            "missing_delta": self.missing_delta,
            "bad_ltp": self.bad_ltp,
            "duplicate_contracts": (
                self.duplicate_contracts
            ),
        }


class CaptureQualityMonitor:
    """Validates each option-stream snapshot before warehouse persistence."""

    def __init__(
        self,
        *,
        minimum_rows: int = 100,
        minimum_expiries: int = 2,
        maximum_missing_delta_pct: float = 20.0,
    ) -> None:
        self.minimum_rows = minimum_rows
        self.minimum_expiries = minimum_expiries
        self.maximum_missing_delta_pct = (
            maximum_missing_delta_pct
        )

    def evaluate(
        self,
        snapshot: pd.DataFrame,
    ) -> CaptureQualityResult:
        issues: list[str] = []
        warnings: list[str] = []

        row_count = len(snapshot)

        if snapshot.empty:
            return CaptureQualityResult(
                is_usable=False,
                issues=[
                    "empty_snapshot"
                ],
            )

        expiry_count = int(
            snapshot["expiry"].nunique()
        )

        missing_ltp = int(
            snapshot["ltp"].isna().sum()
        )

        missing_delta = int(
            snapshot["delta"].isna().sum()
        )

        bad_ltp = int(
            (
                snapshot["ltp"].notna()
                & (snapshot["ltp"] <= 0)
            ).sum()
        )

        duplicate_contracts = int(
            snapshot.duplicated(
                subset=[
                    "ts",
                    "instrument_token",
                ]
            ).sum()
        )

        if row_count < self.minimum_rows:
            issues.append(
                "insufficient_rows"
            )

        if (
            expiry_count
            < self.minimum_expiries
        ):
            warnings.append(
                "insufficient_expiries"
            )

        if missing_ltp:
            issues.append(
                "missing_ltp"
            )

        if bad_ltp:
            issues.append("bad_ltp")

        if duplicate_contracts:
            issues.append(
                "duplicate_contracts"
            )

        missing_delta_pct = (
            missing_delta / row_count * 100
        )

        if (
            missing_delta_pct
            > self.maximum_missing_delta_pct
        ):
            warnings.append(
                "high_missing_delta"
            )

        return CaptureQualityResult(
            is_usable=not issues,
            issues=issues,
            warnings=warnings,
            row_count=row_count,
            expiry_count=expiry_count,
            missing_ltp=missing_ltp,
            missing_delta=missing_delta,
            bad_ltp=bad_ltp,
            duplicate_contracts=(
                duplicate_contracts
            ),
        )


class CaptureQualityWriter:
    """Persists per-snapshot quality records to Parquet."""

    def __init__(
        self,
        output_dir: str | Path,
    ) -> None:
        self.output_dir = Path(
            output_dir
        )

    def write(
        self,
        *,
        underlying: str,
        trade_date: str,
        snapshot_ts: datetime,
        result: CaptureQualityResult,
    ) -> Path:
        record = {
            "ts": [snapshot_ts],
            "underlying": [underlying],
            "trade_date": [trade_date],
            **{
                key: [value]
                for key, value in result.as_dict().items()
                if key not in {
                    "issues",
                    "warnings",
                }
            },
            "issues": [
                ",".join(result.issues)
            ],
            "warnings": [
                ",".join(result.warnings)
            ],
        }

        frame = pd.DataFrame(record)

        target_dir = (
            self.output_dir
            / f"underlying={underlying}"
            / f"year={snapshot_ts.year:04d}"
            / f"month={snapshot_ts.month:02d}"
        )

        target_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        target = (
            target_dir
            / f"capture_quality_{trade_date}.parquet"
        )

        if target.exists():
            existing = pd.read_parquet(
                target
            )
            frame = pd.concat(
                [existing, frame],
                ignore_index=True,
            )

        frame.to_parquet(
            target,
            index=False,
        )

        return target