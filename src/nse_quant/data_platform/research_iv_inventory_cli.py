"""Plan-first artifact recovery inventory; never execute recovery actions."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

VERSION = "research-iv-artifact-inventory-cli@1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not 0 < len(args.artifact_root) <= 2048 or any(
        ord(char) < 32 for char in args.artifact_root
    ):
        parser.error("Bounded nonempty artifact root string required")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "version": VERSION,
                    "artifact_root_as_supplied": args.artifact_root,
                    "filesystem_checked": False,
                    "read_only_execution": True,
                    "stage_ownership_checked": False,
                    "destructive_actions_authorized": False,
                    "publication_asserted": False,
                    "decision_eligibility_asserted": False,
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        from nse_quant.data_platform import research_iv_artifact_files as profile
        from nse_quant.data_platform.research_iv_artifact_inventory import (
            MAX_ARTIFACT_BYTES,
            MAX_ENTRIES,
            inventory_research_iv_artifacts,
        )

        if (
            profile.VERSION != "research-iv-artifact-files@1"
            or profile.MAX_BYTES != MAX_ARTIFACT_BYTES
            or profile.MAX_FILES != MAX_ENTRIES
            or profile.SUFFIX != ".research-iv.json"
        ):
            raise ValueError("IV_INVENTORY_FILE_PROFILE_UNSUPPORTED")
        value = inventory_research_iv_artifacts(Path(args.artifact_root))
        output = asdict(value)
        output["read_only_execution"] = True
        raw = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode()) > 262144:
            raise ValueError("IV_INVENTORY_DIAGNOSTIC_BYTE_LIMIT")
    except Exception:
        print(json.dumps({"status": "FAILED", "reason_code": "IV_ARTIFACT_INVENTORY_FAILED"}))
        return 1
    print(raw)
    return 0 if value.unchanged_observed else 2


if __name__ == "__main__":
    raise SystemExit(main())
