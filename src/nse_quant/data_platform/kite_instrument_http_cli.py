"""Plan-first acquisition. Live execution requires both explicit gates."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from nse_quant.data_platform.kite_instrument_http import (
    CAPTURE_VERSION,
    HOST,
    HttpPolicy,
    KiteHttpCredentials,
    request_path,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-db", type=Path, required=True)
    parser.add_argument("--capture-session-id", required=True)
    parser.add_argument("--exchange")
    parser.add_argument("--actor", default="manual")
    parser.add_argument("--code-revision", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.capture_session_id):
        parser.error("Session identity must be 1-128 ASCII letters/digits/underscore/dot/hyphen")
    try:
        path = request_path(args.exchange)
    except ValueError:
        parser.error("Exchange must be 2-8 uppercase ASCII letters")
    plan = {
        "command": "ingest.kite_instruments_http@1",
        "capture_version": CAPTURE_VERSION,
        "url": "https://" + HOST + path,
        "method": "GET",
        "capture_session_id": args.capture_session_id,
        "bronze_db": str(args.bronze_db.resolve()),
        "actor": args.actor,
        "code_revision": args.code_revision,
        "initialize": args.initialize,
        "policy": asdict(HttpPolicy()),
        "credentials_included": False,
        "redirects": False,
        "automatic_retries": False,
        "session_availability_verified": False,
    }
    if not args.execute:
        print(json.dumps({"status": "PLANNED", "plan": plan}))
        return 0
    if not args.allow_network:
        parser.error("Execution requires separately reviewed --allow-network")
    if not args.actor.strip() or not args.code_revision.strip():
        parser.error("Execution requires actor and code revision")
    if not args.bronze_db.is_file() and not args.initialize:
        parser.error("Explicit --initialize required for new dedicated Bronze DB")
    try:
        credentials = KiteHttpCredentials(
            os.environ.get("KITE_API_KEY", ""), os.environ.get("KITE_ACCESS_TOKEN", "")
        )
    except ValueError:
        print(json.dumps({"status": "FAILED", "reason_code": "CREDENTIALS_UNAVAILABLE"}))
        return 1
    import duckdb

    from nse_quant.data_platform.kite_instrument_http_service import (
        HttpAcquisitionRejected,
        acquire_instrument_reference,
    )

    try:
        with duckdb.connect(str(args.bronze_db)) as conn:
            result = acquire_instrument_reference(
                conn,
                credentials,
                capture_session_id=args.capture_session_id,
                actor_id=args.actor,
                code_revision=args.code_revision,
                exchange=args.exchange,
                initialize=args.initialize,
            )
    except HttpAcquisitionRejected as error:
        print(json.dumps(asdict(error.result)))
        return 1
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "HTTP_ACQUISITION_FAILED"}))
        return 1
    print(json.dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
