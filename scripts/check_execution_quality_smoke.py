"""Inspect execution-quality evidence in a captured paper-loop log."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


def read_log(path: Path) -> str:
    raw = path.read_bytes()

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")

    if b"\x00" in raw:
        return raw.decode("utf-16-le")

    return raw.decode("utf-8-sig")


def extract_plugin(line: str) -> dict[str, Any] | None:
    """Extract a balanced plugin dictionary without evaluating code."""
    key = "'execution_quality'"
    position = line.find(key)

    if position < 0:
        return None

    start = line.find("{", position + len(key))

    if start < 0:
        raise ValueError("Plugin key found without a dictionary")

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
                value = ast.literal_eval(line[start : index + 1])

                if not isinstance(value, dict):
                    raise ValueError("Plugin payload is not a dictionary")

                return value

    raise ValueError("Plugin dictionary is truncated or spans multiple lines")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "log",
        nargs="?",
        default="execution_quality_smoke.txt",
    )
    args = parser.parse_args()

    path = Path(args.log)

    if not path.is_file():
        parser.error(f"Log not found: {path}")

    lines = read_log(path).splitlines()
    payloads: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    error_lines: list[str] = []
    completion_lines: list[str] = []

    for number, line in enumerate(lines, start=1):
        if "'execution_quality'" in line:
            try:
                payload = extract_plugin(line)
                if payload is not None:
                    payloads.append(payload)
            except (ValueError, SyntaxError, RecursionError) as exc:
                parse_errors.append(f"Line {number}: {exc}")

        if (
            "Traceback (most recent call last):" in line
            or "'status': 'loop_error'" in line
            or '"status": "loop_error"' in line
            or ("Evidence plugin " in line and " failed:" in line)
        ):
            error_lines.append(f"Line {number}: {line}")

        if (
            "paper loop completed" in line.lower()
            or "paper loop failed" in line.lower()
            or "replay exhausted" in line.lower()
        ):
            completion_lines.append(f"Line {number}: {line}")

    print(f"Parsed execution-quality payloads: {len(payloads)}")

    if payloads:
        latest = payloads[-1]
        summary = {key: value for key, value in latest.items() if key != "contracts"}

        print("\nLATEST SUMMARY")
        print(json.dumps(summary, indent=2, default=str))

        contracts = latest.get("contracts", [])

        if contracts:
            contract = contracts[0]
            print("\nFIRST CONTRACT DIAGNOSTICS")
            print(
                json.dumps(
                    {
                        key: contract.get(key)
                        for key in (
                            "instrument_token",
                            "tradingsymbol",
                            "price_reason",
                            "spread_absolute",
                            "spread_fraction",
                            "exchange",
                            "receipt",
                            "trade",
                            "oi",
                            "volume",
                            "usable",
                            "complete",
                            "reasons",
                        )
                    },
                    indent=2,
                    default=str,
                )
            )
        else:
            print("\nNo per-contract diagnostics found.")

    print("\nERROR MARKERS")
    print("\n".join(error_lines) if error_lines else "None found.")

    print("\nPARSE ERRORS")
    print("\n".join(parse_errors) if parse_errors else "None.")

    print("\nCOMPLETION MARKERS")
    print(
        "\n".join(completion_lines)
        if completion_lines
        else "None found; full-run completion is not established by this log."
    )

    return 1 if error_lines or parse_errors or not payloads else 0


if __name__ == "__main__":
    raise SystemExit(main())
