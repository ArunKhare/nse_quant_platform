# Durable audited admission-input receipt capture

## Baseline / actual source inspection
User baseline 9ef2f23, QA/tests passed, local/origin aligned by provided Git log.
Local checkout/branch/HEAD cannot be independently inspected. This turn inspected
actual publication_admission.py model/request/receipt fields, variable-length reasons
annotation, exact identity/encode/replay and public assessment API, plus its docs
and native publication context. Existing policy/codec/reader/Ruff/mypy fixes are
not regenerated or overwritten. Migration and source eligibility remain unchanged.

## Add only
src/nse_quant/data_platform/admission_capture.py
src/nse_quant/data_platform/admission_capture_cli.py
scripts/ingest/capture_publication_admission.py
tests/data_platform/test_admission_capture.py
docs/ADMISSION_CAPTURE_STORAGE.md

## This increment
Dedicated file-backed decision_inputs store with immutable native contract/policy
registry, complete exact receipt bytes and frozen inputs, accepted/rejected outcome
metadata, per-request reassessment history and audited attempt links. Fresh native
assessment per attempt, not offline receipt import. Domain contract/definition/
receipt/link writes are atomic; final audit is separate. Exact retries deduplicate
content while preserving attempts, timestamps and first job. Corruption/unsupported
versions/legacy output targets reject; old records are never updated/deleted.
These are post-publication business records, not medallion observations/analytics:
no fake Gold/Silver layer metadata or weakened DatasetContract enum is introduced.

API:
capture_publication_admission(publications, target, publication_id=...,
    request=AdmissionRequest(...), actor_id=..., code_revision=..., initialize=False)

Plan:
uv run python scripts/ingest/capture_publication_admission.py --publication-db <registry.duckdb> --receipt-db <admission-receipts.duckdb> --publication-id <64hex> --use-case ARCHIVED_RESEARCH_ANALYSIS

Execution adds --execute --actor <actor> --code-revision <revision> and --initialize
for a new dedicated receipt DB. Parent directory must exist. Publication source is
read-only. POINT_IN_TIME_DECISION also needs --knowledge-cutoff <aware-ISO> and
--economic-at <aware-ISO>; current research-only input remains rejected.
COMMITTED/exit 0 records a completed capture even when domain status=REJECTED; it
is not trading permission. Raw receipt rows or successful fresh retries cannot
manufacture an earlier incomplete audit's success. See storage doc before execution.

## Safe apply / mandatory local QA
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store; reconcile
9ef2f23 or newer without resetting/discarding work. Compare actual native admission
and audit APIs. Copy only five repository additions. STOP on existing paths and
compare rather than overwrite. Run verify-local.ps1 from extracted bundle; review
untracked additions as well as git diff. No existing deps/tests/configs/typing or
architecture weakened. No source data loaded, migrated, acquired or published.

## Verification disclosure
29 focused tests passed under Python 3.12.8 with actual file-backed DuckDB domain/
audit transactions. Covers full frozen-byte replay, native contract/definition,
rejection capture, exact retry/reassessment, alias/legacy/schema/policy/byte/history
limits, rollback of contract+definition+receipt+attempt, incomplete final audit,
no history revival, non-UTC request retries, quoted namespace ambiguity, no-I/O
plan and CLI read-only/source-error boundaries.
In repository tests only the publication verifier boundary is substituted; actual
policy/receipt codecs are imported. The sandbox cannot read checkout modules, so
baseline audit was reconstructed and policy/codec/model behavior used an interface
harness. Those harness dependencies are NOT shipped. These tests do not establish
full source/audit authenticity, decision execution or strategy replay. Full required
QA, Ruff and mypy were not run here and remain mandatory locally. Python line
length, static import scan, patch whitespace and ZIP/file checksums were checked.

Suggested commit after local QA:
feat(data-platform): persist audited admission receipts and frozen decision inputs

Next boundary: verified captured-receipt/provenance consumption, not automatic
promotion of research data. Loading/migration remains held until platform acceptance.
