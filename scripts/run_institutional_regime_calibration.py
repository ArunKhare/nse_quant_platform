"""Run the diagnostic-only institutional regime walk-forward report from CSV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from nse_quant.research.institutional_regime_calibration import (
    CalibrationObservation,
    build_institutional_regime_calibration_report,
    render_calibration_report_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostic-only NIFTY regime threshold calibration report."
    )
    parser.add_argument("--input", required=True, type=Path, help="Prepared daily calibration CSV.")
    parser.add_argument("--output", required=True, type=Path, help="Markdown report output path.")
    parser.add_argument("--source-manifest", type=Path, help="Optional JSON describing upstream data sources.")
    parser.add_argument("--training-sessions", type=int, default=360)
    parser.add_argument("--test-sessions", type=int, default=63)
    parser.add_argument("--step-sessions", type=int, default=63)
    return parser


def _load_rows(path: Path) -> list[CalibrationObservation]:
    required = {
        "session", "ivp", "iv30_minus_iv90", "rr25", "adx14", "plus_di14",
        "minus_di14", "er20", "chop14", "atr14", "atr_percentile",
        "bandwidth_percentile", "range_position", "change20", "sma20_slope",
        "realized_variance",
    }
    rows: list[CalibrationObservation] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = sorted(required - fields)
        if missing:
            raise ValueError(f"missing_required_csv_columns:{','.join(missing)}")
        for line_number, row in enumerate(reader, start=2):
            try:
                values: dict[str, Any] = {
                    key: float(row[key]) for key in required if key != "session"
                }
                rows.append(CalibrationObservation(
                    session=date.fromisoformat(row["session"]),
                    **values,
                ))
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"invalid_calibration_csv_row:{line_number}") from exc
    return rows


def main() -> int:
    args = _parser().parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    rows = _load_rows(args.input)
    manifest: dict[str, Any] = {
        "input_file": args.input.name,
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "input_rows": len(rows),
        "feature_contract": "institutional_regime_calibration_csv_v1",
    }
    if args.source_manifest is not None:
        manifest_path = args.source_manifest
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)
        supplied = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(supplied, dict):
            raise ValueError("source_manifest_must_be_json_object")
        manifest["upstream_sources"] = supplied

    report = build_institutional_regime_calibration_report(
        rows,
        source_manifest={key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
                         for key, value in manifest.items()},
        training_sessions=args.training_sessions,
        test_sessions=args.test_sessions,
        step_sessions=args.step_sessions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_calibration_report_markdown(report), encoding="utf-8")
    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"status={report['status']}")
    print(f"markdown_report={args.output}")
    print(f"json_report={json_path}")
    return 0 if report["status"] == "DIAGNOSTIC_REPORT_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
