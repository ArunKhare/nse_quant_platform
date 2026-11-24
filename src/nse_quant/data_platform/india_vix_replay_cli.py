"""Manual read-only VIX replay. No store initialization, captures or publications."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import duckdb

VERSION = "india-vix-replay-report@1"
EXIT_VALID = 0
EXIT_ERROR = 2
EXIT_REJECTED = 3
OBSERVATION_FIELDS = (
    "as_of",
    "source_time",
    "received_at",
    "value_percent",
    "iv30",
    "raw_payload_sha256",
    "instrument_reference_sha256",
    "instrument_token",
    "quote_key",
    "within_regular_time_window",
    "session_calendar_verified",
    "session_is_open",
    "version",
    "iv30_source",
    "mode",
    "decision_eligibility_asserted",
)


def _revision(value: str) -> str:
    if re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise argparse.ArgumentTypeError("revision must be exactly 64 lowercase hexadecimal characters")
    return value


def _paths(bronze: Path, silver: Path) -> tuple[Path, Path]:
    # strict resolution rejects missing paths before DuckDB is allowed to open anything.
    bronze, silver = bronze.resolve(strict=True), silver.resolve(strict=True)
    if not bronze.is_file() or not silver.is_file():
        raise ValueError("EXISTING_DATABASE_FILES_REQUIRED")
    if bronze.samefile(silver):
        raise ValueError("SEPARATE_DATABASE_FILES_REQUIRED")
    return bronze, silver


def _replay(bronze: Any, silver: Any, *, revision_id: str) -> dict[str, Any]:
    # Import only on explicit invocation, never as a side effect of --help.
    from nse_quant.data_platform.india_vix_recording import replay_vix_silver

    return replay_vix_silver(bronze, silver, revision_id=revision_id)


def _result(record: dict[str, Any], revision: str) -> tuple[dict[str, Any], int]:
    if not isinstance(record, dict) or record.get("decision_eligibility_asserted") is not False:
        raise ValueError("OBSERVATION_ONLY_RECORD_REQUIRED")
    quality = record.get("quality_state")
    observation = record.get("observation")
    reason = record.get("rejection_reason")
    if quality == "valid_observation":
        if (
            not isinstance(observation, dict)
            or observation.get("decision_eligibility_asserted") is not False
            or observation.get("iv30_source") != "india_vix"
            or observation.get("mode") != "observation"
            or reason is not None
        ):
            raise ValueError("OBSERVATION_ONLY_VIX_OUTPUT_REQUIRED")
        observation = {key: observation[key] for key in OBSERVATION_FIELDS if key in observation}
        status, code = "verified_valid_observation", EXIT_VALID
    elif quality == "rejected":
        if observation is not None or not isinstance(reason, str) or not 1 <= len(reason) <= 128:
            raise ValueError("REJECTED_RECORD_REQUIRED")
        if re.fullmatch(r"[A-Za-z0-9_]+", reason) is None:
            raise ValueError("BOUNDED_REJECTION_CODE_REQUIRED")
        status, code = "verified_rejected_evidence", EXIT_REJECTED
    else:
        raise ValueError("KNOWN_QUALITY_STATE_REQUIRED")
    # Report normalized output only. Do not dump raw payloads, paths or exception strings.
    report = dict(
        report_version=VERSION,
        status=status,
        replay_verified=True,
        revision_id=revision,
        quality_state=quality,
        rejection_reason=reason,
        observation=observation,
        decision_eligibility_asserted=False,
    )
    return report, code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", required=True, type=Path)
    parser.add_argument("--silver-db", required=True, type=Path)
    parser.add_argument("--revision-id", required=True, type=_revision)
    args = parser.parse_args(argv)
    try:
        bp, sp = _paths(args.bronze_db, args.silver_db)
        with ExitStack() as stack:
            bronze = stack.enter_context(duckdb.connect(str(bp), read_only=True))
            silver = stack.enter_context(duckdb.connect(str(sp), read_only=True))
            report, code = _result(_replay(bronze, silver, revision_id=args.revision_id), args.revision_id)
        rendered = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except Exception:
        # Never echo exception text: DuckDB/JSON errors may contain source payloads or paths.
        print(
            json.dumps(
                dict(
                    report_version=VERSION,
                    status="verification_failed",
                    replay_verified=False,
                    revision_id=args.revision_id,
                    error_code="VIX_REPLAY_VERIFICATION_FAILED",
                    decision_eligibility_asserted=False,
                ),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_ERROR
    print(rendered)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
