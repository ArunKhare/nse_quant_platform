"""Run from the repository root. Review git diff before committing."""

from pathlib import Path

fixture = Path("tests/data_platform/test_underlying_assertion_snapshot.py")
acceptance = Path("src/nse_quant/data_platform/native_authority_evidence_completeness_report_acceptance.py")
old_schema = '        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {reader._quote(schema)}")'
new_schema = (
    '        schema_path = ".".join(map(reader._quote, (request.param, schema)))\n'
    '        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_path}")'
)
old_return = '        "accepted": True,'
new_return = '        "accepted": accepted,'
changes = []
for path, old, new in ((fixture, old_schema, new_schema), (acceptance, old_return, new_return)):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    normalized = text.replace("\r\n", "\n")
    if old in normalized:
        if normalized.count(old) != 1:
            raise SystemExit(f"Ambiguous edit; no writes performed: {path}")
        updated = normalized.replace(old, new, 1)
        newline = "\r\n" if b"\r\n" in raw else "\n"
        changes.append((path, updated.replace("\n", newline).encode("utf-8")))
    elif new not in normalized:
        raise SystemExit(f"Source differs; no writes performed: {path}")
for path, content in changes:
    path.write_bytes(content)
    print(f"Updated {path}")
print(f"Applied {len(changes)} guarded edits; no tests executed by this script.")
