"""Inspect observational evidence in captured paper-loop logs.
Check term structure
Use this instead of the previous command:

powershell
uv run python scripts/check_execution_quality_smoke.py output.txt `
--plugin institutional_regime`
--component term_structure

Other useful commands
---------------------
All institutional components:
------
powershell
uv run python scripts/check_execution_quality_smoke.py output.txt `
--plugin institutional_regime
IV-state component only:

powershell
uv run python scripts/check_execution_quality_smoke.py output.txt `
--plugin institutional_regime `
--component iv_state
Execution-quality evidence:

powershell
uv run python scripts/check_execution_quality_smoke.py execution_quality_smoke.txt `
--plugin execution_quality

The script parses complete, single-line plugin dictionaries in either
Python-literal or JON format.
Truncated or multi-line payloads are reported as parse errors rather than silently
treated as valid.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


def read_log(path: Path) -> str:
    raw = path.read_bytes()

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")

    if b"\x00" in raw:
        return raw.decode("utf-16-le")

    return raw.decode("utf-8-sig")


def plugin_pattern(plugin: str) -> re.Pattern[str]:
    return re.compile(rf"""(?P<quote>['"]){re.escape(plugin)}(?P=quote)\s*:\s*\{{""")


def extract_plugin(
    line: str,
    plugin: str = "execution_quality",
) -> dict[str, Any] | None:
    """Extract a balanced Python-literal or JSON plugin dictionary."""
    match = plugin_pattern(plugin).search(line)

    if match is None:
        return None

    start = match.end() - 1
    depth = 0
    quote: str | None = None
    escaped = False

    for index in range(start, len(line)):
        char = line[index]

        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                text = line[start : index + 1]

                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    value = ast.literal_eval(text)

                if not isinstance(value, dict):
                    raise ValueError("Plugin payload is not a dictionary")

                return value

    raise ValueError("Plugin dictionary is truncated or spans multiple lines")


def display_json(title: str, value: Any) -> None:
    print(f"\n{title}")
    print(json.dumps(value, indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Inspect plugin evidence without changing data or settings.")
    )
    parser.add_argument(
        "log",
        nargs="?",
        default="execution_quality_smoke.txt",
    )
    parser.add_argument(
        "--plugin",
        default="execution_quality",
        help="Evidence plugin name",
    )
    parser.add_argument(
        "--component",
        default=None,
        help="Optional component, such as term_structure or iv_state",
    )
    args = parser.parse_args()

    path = Path(args.log)

    if not path.is_file():
        parser.error(f"Log not found: {path}")

    try:
        lines = read_log(path).splitlines()
    except UnicodeError as exc:
        parser.error(f"Cannot decode log: {exc}")

    target_pattern = plugin_pattern(args.plugin)
    loop_error_pattern = re.compile(r"""['"]status['"]\s*:\s*['"]loop_error['"]""")

    payloads: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    error_lines: list[str] = []
    lifecycle_lines: list[str] = []

    for number, line in enumerate(lines, start=1):
        if target_pattern.search(line):
            try:
                payload = extract_plugin(line, args.plugin)
                if payload is not None:
                    payloads.append(payload)
            except (
                ValueError,
                SyntaxError,
                RecursionError,
            ) as exc:
                parse_errors.append(f"Line {number}: {exc}")

        lowered = line.lower()

        if (
            "Traceback (most recent call last):" in line
            or loop_error_pattern.search(line)
            or ("evidence plugin " in lowered and " failed:" in lowered)
            or "paper loop failed" in lowered
        ):
            error_lines.append(f"Line {number}: {line}")

        if any(
            marker in lowered
            for marker in (
                "paper loop completed",
                "paper loop failed",
                "replay exhausted",
                "paper loop interrupted",
                "kill switch active",
            )
        ):
            lifecycle_lines.append(f"Line {number}: {line}")

    print(f"Plugin: {args.plugin}")
    print(f"Parsed payloads: {len(payloads)}")

    component_missing = False
    plugin_errors = [
        {
            "payload_number": index,
            "error_type": payload.get("error_type"),
            "error": payload.get("error"),
        }
        for index, payload in enumerate(payloads, start=1)
        if payload.get("error_type") is not None or payload.get("error") is not None
    ]

    if payloads:
        latest = payloads[-1]

        excluded = {"contracts"}

        if args.component is not None:
            excluded.add("components")

        summary = {key: value for key, value in latest.items() if key not in excluded}
        display_json("LATEST SUMMARY", summary)

        if args.component is not None:
            components = latest.get("components")

            if isinstance(components, dict) and args.component in components:
                display_json(
                    f"COMPONENT: {args.component}",
                    components[args.component],
                )
            else:
                component_missing = True
                print(f"\nRequested component not found: {args.component}")

        if args.plugin == "execution_quality":
            contracts = latest.get("contracts")

            if isinstance(contracts, list) and contracts:
                display_json(
                    "FIRST CONTRACT DIAGNOSTICS",
                    contracts[0],
                )
            else:
                print("\nNo per-contract diagnostics found.")

    print("\nERROR MARKERS")
    print("\n".join(error_lines) if error_lines else "None found.")

    display_json("PLUGIN ERROR PAYLOADS", plugin_errors)

    print("\nPARSE ERRORS")
    print("\n".join(parse_errors) if parse_errors else "None.")

    print("\nLIFECYCLE MARKERS")
    print(
        "\n".join(lifecycle_lines)
        if lifecycle_lines
        else ("None found; full-run completion is not established by this log.")
    )

    print(
        "\nThis checks captured output only. "
        "Incomplete evidence is not automatically a failure, "
        "and exit code zero does not certify process completion."
    )

    failed = (
        not payloads
        or bool(parse_errors)
        or bool(error_lines)
        or bool(plugin_errors)
        or component_missing
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
