"""Explicit offline S2 materialization commands; default is no-I/O planning."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise ValueError("S2_INPUT_FILE_BYTE_BOUND")
    return raw


def _write_new(path: Path, raw: bytes) -> None:
    """Single-owner directory; hard-link final file without replacement.

    File fsync is performed. Directory fsync/power-loss durability is not asserted.
    A final file surviving later cleanup failure is never deleted or adopted here.
    """
    path = path.absolute()
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ValueError("S2_REDIRECTED_OUTPUT_PARENT")
    if path.exists() or path.is_symlink():
        raise FileExistsError("S2_OUTPUT_EXISTS_REVIEW_REQUIRED")
    descriptor, name = tempfile.mkstemp(prefix=".s2-pending-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("S2_INCOMPLETE_OUTPUT_WRITE")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--db", type=Path, required=True)
    init.add_argument("--actor", required=True)
    init.add_argument("--code-revision", required=True)
    eod = commands.add_parser("prepare-eod")
    eod.add_argument("--csv", type=Path, required=True)
    eod.add_argument("--expected-csv-sha256", required=True)
    eod.add_argument("--source-reference", required=True)
    eod.add_argument("--received-at", required=True)
    eod.add_argument("--as-of", required=True)
    eod.add_argument("--date-column", required=True)
    eod.add_argument("--close-column", required=True)
    eod.add_argument("--date-format", default="%Y-%m-%d")
    eod.add_argument("--output", type=Path, required=True)
    minute = commands.add_parser("prepare-minute")
    minute.add_argument("--revision", action="append", required=True)
    minute.add_argument("--bronze", type=Path, required=True)
    minute.add_argument("--vix-silver", type=Path, required=True)
    minute.add_argument("--output", type=Path, required=True)
    persist = commands.add_parser("persist")
    persist.add_argument("--db", type=Path, required=True)
    persist.add_argument("--artifact", type=Path, required=True)
    persist.add_argument("--actor", required=True)
    persist.add_argument("--code-revision", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--db", type=Path, required=True)
    replay.add_argument("--kind", choices=["india_vix_eod_history", "india_vix_minute_bars"], required=True)
    replay.add_argument("--output", type=Path, required=True)
    for item in (persist, replay):
        item.add_argument("--observation-id", required=True)
        item.add_argument("--expected-sha256", required=True)
        item.add_argument("--bronze", type=Path)
        item.add_argument("--vix-silver", type=Path)
    for item in (init, eod, minute, persist, replay):
        item.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(action=args.command, status="PLANNED_NO_IO", decision_eligibility_asserted=False)))
        return 0
    from nse_quant.data_platform import s2_series_materialization as api

    if args.command == "prepare-eod":
        from nse_quant.analytics import s2_iv30_history as history

        raw = history.build_history(
            raw_csv=_read(args.csv, history.MAX_RAW),
            expected_raw_sha256=args.expected_csv_sha256,
            source_reference=args.source_reference,
            received_at=args.received_at,
            as_of=args.as_of,
            date_column=args.date_column,
            close_column=args.close_column,
            date_format=args.date_format,
        )
        artifact = api.prepare_eod(raw)
        _write_new(args.output, artifact)
        print(json.dumps(dict(status="PREPARED_NOT_PUBLISHED", digest=api.sha(artifact))))
        return 0
    import duckdb

    with ExitStack() as stack:

        def connect(path: Path, *, readonly: bool):
            if readonly and not path.is_file():
                raise ValueError("S2_EXISTING_SOURCE_FILE_REQUIRED")
            return stack.enter_context(duckdb.connect(str(path), read_only=readonly))

        sources: dict[str, Any] = {}
        if args.command in {"prepare-minute", "persist", "replay"}:
            if bool(args.bronze) != bool(args.vix_silver):
                raise ValueError("S2_BOTH_MINUTE_SOURCES_REQUIRED")
            if args.bronze:
                sources = dict(
                    bronze=connect(args.bronze, readonly=True), vix_silver=connect(args.vix_silver, readonly=True)
                )
        if args.command == "prepare-minute":
            raw = api.prepare_minutes(**sources, revision_ids=args.revision)
            _write_new(args.output, raw)
            result = dict(status="PREPARED_NOT_PUBLISHED", digest=api.sha(raw))
        elif args.command == "init":
            if args.db.exists() or args.db.is_symlink():
                raise FileExistsError("S2_NEW_DATABASE_PATH_REQUIRED")
            api._actor(args.actor, args.code_revision)
            api.initialize(connect(args.db, readonly=False), actor_id=args.actor, code_revision=args.code_revision)
            result = dict(status="INITIALIZED_NOT_PUBLISHED")
        else:
            if not args.db.is_file():
                raise ValueError("S2_EXISTING_MATERIALIZATION_STORE_REQUIRED")
            if args.command == "persist":
                raw = _read(args.artifact, api.MAX_BYTES)
                result = api.persist(
                    connect(args.db, readonly=False),
                    raw=raw,
                    observation_id=args.observation_id,
                    expected_sha256=args.expected_sha256,
                    actor_id=args.actor,
                    code_revision=args.code_revision,
                    **sources,
                )
            else:
                raw = api.replay(
                    connect(args.db, readonly=True),
                    kind=args.kind,
                    observation_id=args.observation_id,
                    expected_sha256=args.expected_sha256,
                    **sources,
                )
                _write_new(args.output, raw)
                result = dict(status="REPLAYED_NOT_PUBLISHED", digest=api.sha(raw))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
