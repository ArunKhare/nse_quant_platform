# FS1c: native capture health, recovery planning and drain gating

Status: source-preserving diagnostics and planning. No automatic source repair.
Requires QA-passed A1/A2, corrected FS1a and FS1b native capture. Silver decoding is
intentionally a separate subsequent package, not hidden inside recovery.

## Purpose

Make incomplete/failed evidence inspectable without truncating it, deleting records,
rewriting seals or declaring failed capture successful. Identify contiguous valid
prefixes for human review. A recovery candidate is not automatically ingestible data.

## Implemented

capture_health.py: bounded file/envelope/seal/audit inspection and evidence fingerprint.
capture_health_cli.py: stdout inspection; optional audited plan export outside source.
scripts/inspect/inspect_capture_health.py: thin CLI.
drain_capture.py: replaces native drainer with a health-gated version 2, retaining
stable segment batch identities and FS1a idempotency. No legacy execution path.

Health states include CLOSED_VERIFIED, EMPTY_CLOSED_VERIFIED, FAILED_WITH_EVIDENCE,
CLOSED_REQUIRES_REVIEW, INCOMPLETE_REQUIRES_REVIEW and UNSTABLE_OBSERVATION.
Only a nonempty, closed, structurally verified, successfully audited session is
eligible for normal draining. This is capture-integrity eligibility, not quote quality
or research/trading eligibility. An empty clean session is not useful market data.

## Inspection contract

Read original source using normal read-only file operations and read-only DuckDB.
Never initialize source schemas, update audit events, truncate a tail, skip a corrupt
middle record, regenerate a seal or change original receipt identities/timestamps.

Checks include:
- start/final version and source/session identity;
- capture.kite_raw@1 audit state, not an unrelated successful job;
- segment filename order and local receipt sequence;
- bounded UTF-8 JSON envelope parsing, base64 and aware receipt timestamps;
- payload representation and native origin contract;
- checksums, bytes, record counts and listed/orphan seals;
- partial/unterminated tails and first invalid offsets;
- source size/mtime and metadata changes during inspection;
- explicit per-line, segment-count, segment-size and total-byte budgets.

No raw payload, decoded account message or base64 payload is included in reports.
The source path and session identity remain business metadata; secure report access.
A busy/unreadable audit DB is not called corrupt. A RUNNING job does not prove its
process is alive, and a missing final file does not distinguish active vs crashed.
This is an offline evidence inspector, not a heartbeat/failover service.

Default budgets: 4096 segments, 8 MiB per segment, 1 GiB total data, 2 MiB per line,
1 MiB metadata file. Budget exhaustion explicitly denies automatic ingestion.
Directory enumeration is bounded. A limited evidence fingerprint describes inspected
coverage and limits; it is not a cryptographic proof about uninspected files.

## Prefix semantics

valid_prefix_bytes and complete_records describe only the contiguous validated prefix
up to the first bad/unterminated record. Later plausible records are not silently
skipped into a repaired stream. A newline-terminated record is required even if an
unterminated tail happens to parse as JSON. The native writer acknowledges complete
newline envelopes, so tail completeness is not inferred.

An unsealed stable segment may produce REVIEW_PREFIX_AS_NEW_EVIDENCE_ONLY. Every
candidate has auto_ingest=False. No candidates are proposed from an unstable observation
or from a sealed file whose contents disagree with its seal. Preserve the source first;
any future approved copy is a separate artifact with recovery provenance, not a rewrite.

## Commands

Read-only report:

    uv run python scripts/inspect/inspect_capture_health.py --session-dir data/bronze/journals/SESSION_ID

Add --require-clean for exit 2 when ordinary draining is not eligible. Default exit 0
means inspection completed, not that capture was healthy.

Publish a review plan (does not execute recovery):

    uv run python scripts/inspect/inspect_capture_health.py --session-dir data/bronze/journals/SESSION_ID --publish-plan --output-root data/capture_reviews --code-revision YOUR_COMMIT

Publication creates a UUID-named output directory, separate inspection audit DB,
content-addressed manifest, health JSON, nonexecuting recovery plan and receipt. It
rechecks the observed evidence fingerprint before publication. It does not lock/freeze
an externally changing source or make a multi-file atomic snapshot. Every actual
recovery operation must revalidate its input fingerprint again.

A failed review publication may leave partial outputs in its own failed run. Verify
its audit state and receipt before treating it as a completed review. No original
capture state changes because a review job succeeds.

## Drain update

Native drainer now requires the health gate before planning or opening a target writer.
It includes evidence fingerprint and inspection limits in its audit plan. Existing
raw-buffer checksum validation and per-segment atomic idempotent appends remain.
The operation version changes to ingest.kite_segments@2 / ingest.kite_segment@2.
The stable batch identity is unchanged, so an already committed segment is not reinserted.

Use --max-inspection-bytes / --max-inspection-segments only after explicit capacity
review when capture budgets legitimately exceed defaults. Failed, incomplete, empty,
resource-limited or audit-unverified sessions are not made ingestible by a flag.
There is no --force-clean or --ignore-corruption escape hatch.

## Limits and next work

Contiguous locally assigned receipt IDs do not prove the broker/network delivered
every market event. Integrity hashes are not signatures/WORM protection against an
attacker who can edit all metadata and hashes. Permissions and off-host preservation
remain operational requirements. No feature freshness/liquidity/expiry coverage grade
is inferred from a clean journal.

Actual recovery execution, source snapshot preservation workflow, operator approval,
auto-resume and capture crash reconciliation are not implemented here. Silver decoding
needs an independently versioned raw packet codec plus instrument metadata and event/
receipt/availability semantics. Do not normalize partial evidence as if it were complete.

## Validation

18 unit/fixture cases passed here with real temporary source files and minimal real
DuckDB audit fixtures. Covered no source changes, positive gating, truncation, corrupt
middle records, checksum failure, missing final/audit states, empty capture, resource
limits, orphan seals, source changes, busy DB, CLI return semantics and output exclusion.
An actual A1/FS1b integration case is included for local execution, not run here.

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Full native drain integration, review publication integration, Windows filesystem
behavior, process-crash, sustained volume, adversarial filesystem and production
acceptance remain local validation. No broker connection or Git commit was performed.
