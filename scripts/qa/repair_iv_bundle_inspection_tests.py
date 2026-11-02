"""Targeted test repair; default plans only. Does not change production or Git state."""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import subprocess
from pathlib import Path

BOUNDARY = "tests/data_platform/test_research_iv_bundle_inspect_boundary.py"
CLI_TEST = "tests/data_platform/test_research_iv_bundle_inspect_cli.py"
MANIFEST = "RESEARCH_IV_BUNDLE_INSPECTION_SHA256SUMS.txt"
HELPER_IMPORT = (
    "from iv_bundle_inspection_fixture_files import bind_fixture_sources, fixture_arguments\n"
)
ADAPTER = """

@pytest.fixture(autouse=True)
def bind_inspection_source_roles(current_bundle_case, monkeypatch):
    sources = current_bundle_case[5]
    with bind_fixture_sources(cli, sources, monkeypatch):
        yield
"""


def _replace(source: str, edits: list[tuple[int, int, str]]) -> str:
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start - 1 : end] = [replacement]
    return "".join(lines)


def transform_boundary(source: str) -> str:
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    selected = [node for node in functions if node.name == "readonly_arguments"]
    if len(selected) != 1 or "bind_inspection_source_roles" in source:
        raise ValueError("BOUNDARY_SOURCE_NOT_EXPECTED_OR_ALREADY_REPAIRED")
    helper = selected[0]
    segment = ast.get_source_segment(source, helper)
    if segment is None or "PRAGMA database_list" not in segment or "conn.close()" not in segment:
        raise ValueError("BOUNDARY_HELPER_CHANGED_REVIEW_REQUIRED")
    assert helper.end_lineno is not None
    replacement = (
        "def readonly_arguments(case):\n    return fixture_arguments(case, cli.PATH_NAMES)\n"
    )
    updated = _replace(source, [(helper.lineno, helper.end_lineno, replacement)])
    # Preserve prior Ruff fixes and every test assertion/body outside this helper.
    tree = ast.parse(updated)
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    if not imports:
        raise ValueError("BOUNDARY_IMPORTS_REQUIRED")
    test_imports = [
        node
        for node in imports
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("test_")
    ]
    if not test_imports:
        raise ValueError("BOUNDARY_FIXTURE_IMPORTS_REQUIRED")
    position = test_imports[0].lineno
    lines = updated.splitlines(keepends=True)
    lines[position - 1 : position - 1] = [HELPER_IMPORT]
    updated = "".join(lines)
    if not any(
        isinstance(node, ast.Import) and any(alias.name == "pytest" for alias in node.names)
        for node in ast.parse(updated).body
    ):
        updated = updated.replace(HELPER_IMPORT, "import pytest\n" + HELPER_IMPORT, 1)
    # Append a local adapter; no shared fixtures or successful native results replaced.
    return updated.rstrip() + "\n" + ADAPTER


def transform_cli_test(source: str) -> str:
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    edits: list[tuple[int, int, str]] = []
    targets = [node for node in functions if node.name == "arguments"]
    if len(targets) != 1:
        raise ValueError("ARGUMENT_HELPER_REQUIRED")
    for node in targets[0].body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "result"
            and isinstance(node.value, ast.List)
            and not node.value.elts
        ):
            assert node.end_lineno is not None
            edits.append((node.lineno, node.end_lineno, "    result: list[str] = []\n"))
    fixed = 0
    for name, reason in (
        (
            "test_bundle_archive_source_alias_rejected_before_connection",
            "SEPARATE_IV_BUNDLE_ARCHIVE",
        ),
        ("test_member_archive_source_alias_rejected", "SEPARATE_IV_MEMBER_ARCHIVE"),
    ):
        matches = [node for node in functions if node.name == name]
        if len(matches) != 1:
            raise ValueError("ALIAS_TEST_CHANGED_REVIEW_REQUIRED")
        for outer in matches[0].body:
            if (
                isinstance(outer, ast.With)
                and len(outer.items) == 1
                and len(outer.body) == 1
                and isinstance(outer.body[0], ast.With)
            ):
                inner = outer.body[0]
                segment = ast.get_source_segment(source, outer)
                if segment is None or reason not in segment or len(inner.body) != 1:
                    raise ValueError("ALIAS_CONTEXT_CHANGED_REVIEW_REQUIRED")
                body = ast.get_source_segment(source, inner.body[0])
                assert body is not None and outer.end_lineno is not None
                replacement = (
                    "    with (\n"
                    f'        pytest.raises(ValueError, match="{reason}"),\n'
                    "        cli._open_inputs(tuple(paths)),\n    ):\n        " + body + "\n"
                )
                edits.append((outer.lineno, outer.end_lineno, replacement))
                fixed += 1
    if fixed != 2 or not edits:
        raise ValueError("EXPECTED_TWO_NESTED_CONTEXTS_REVIEW_REQUIRED")
    return _replace(source, edits)


def prepare(repository: Path) -> dict[str, bytes]:
    before = {name: (repository / name).read_bytes() for name in (BOUNDARY, CLI_TEST, MANIFEST)}
    boundary = transform_boundary(before[BOUNDARY].decode("utf-8-sig"))
    cli_test = transform_cli_test(before[CLI_TEST].decode("utf-8-sig"))
    for raw in (boundary, cli_test):
        compile(raw, "repaired test", "exec")
    changes = {BOUNDARY: boundary.encode(), CLI_TEST: cli_test.encode()}
    manifest = before[MANIFEST].decode("utf-8-sig").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in manifest:
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9_./-]+)", line)
        if match is None or match[2] in seen:
            raise ValueError("OLD_MANIFEST_MALFORMED")
        name = match[2]
        seen.add(name)
        if name in changes:
            line = hashlib.sha256(changes[name]).hexdigest() + "  " + name
        output.append(line)
    if not changes.keys() <= seen:
        raise ValueError("OLD_MANIFEST_MISSING_CHANGED_TESTS")
    changes[MANIFEST] = ("\n".join(output) + "\n").encode()
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    changes = prepare(args.repository)
    if args.apply:
        if args.expected_head is None or re.fullmatch(r"[a-f0-9]{40}", args.expected_head) is None:
            parser.error("Apply requires reviewed full 40-character Git HEAD")
        for command, expected in (
            (["rev-parse", "HEAD"], args.expected_head),
            (["branch", "--show-current"], "feat/medallion-feature-store"),
        ):
            value = subprocess.check_output(
                ["git", "-C", str(args.repository), *command],
                text=True,
            )
            if value.strip() != expected:
                raise ValueError("ACTUAL_GIT_BASELINE_DIFFERS")
        # No all-files atomicity claim: retain working-tree diff and rerun QA on any write failure.
        for name, raw in changes.items():
            (args.repository / name).write_bytes(raw)
    for name, raw in changes.items():
        print(
            ("APPLIED " if args.apply else "PLANNED ")
            + name
            + " "
            + hashlib.sha256(raw).hexdigest()
        )


if __name__ == "__main__":
    main()
