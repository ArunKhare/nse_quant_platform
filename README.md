# Audited quote-feature bundle staging package

## Baseline and interface reconciliation
User baseline 2b29bc4, QA/tests passed, HEAD/origin aligned by supplied Git log.
Local branch/HEAD cannot be accessed independently here. This turn inspected the
current feature_bundle.py full codec/models/bounds, existing bundle tests/docs,
Gold reader, audit.py, contracts.py and manifests.py. Assembly signature is
confirmed by its uploaded tests/docs. New code preserves all existing modules.
No changes to the committed codec, consumer, Gold kernel or existing QA fixes.

## Add only
src/nse_quant/data_platform/bundle_artifacts.py
src/nse_quant/data_platform/quote_bundle_staging.py
src/nse_quant/data_platform/quote_bundle_stage_cli.py
scripts/ingest/stage_quote_feature_bundle.py
tests/data_platform/test_quote_bundle_staging.py
tests/data_platform/test_quote_bundle_stage_cli.py
docs/QUOTE_BUNDLE_STAGING.md

## Implemented
Fresh explicit-pin assembly under audit, file-backed dedicated staging metadata,
root binding, canonical bytes/checksums, fsync-before-hard-link no-replace artifacts,
post-write exact verification, atomic stage/attempt metadata, append-only history
and exact retries. Missing registered files, orphan artifacts, corrupt bytes,
changed root bindings and unsupported state require review; no reseal/adoption.
No publisher, migration, replay or audit-repair path is added.

## Public service / CLI
stage_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold, staging,
    build_ids=(<exact pins>, ...), artifact_root=Path(...), actor_id=...,
    code_revision=..., initialize=False)

Default CLI plan:
uv run python scripts/ingest/stage_quote_feature_bundle.py --bronze-db <bronze.duckdb> --frame-silver-db <frames.duckdb> --reference-silver-db <references.duckdb> --assessment-db <assessments.duckdb> --gold-db <gold.duckdb> --staging-db <bundle-staging.duckdb> --artifact-root <dedicated-artifacts-directory> --build-id <64-lowercase-hex>

Repeat --build-id for additional exact members. Execution adds --execute --actor
<actor> --code-revision <revision>. Add --initialize for a new dedicated metadata
DB. DB parent directory must exist. Artifact directory must not contain any of
the input/output database files. All execution inputs are read-only.
A successful result is SEALED_NOT_PUBLISHED with false publication/eligibility.
No default network, credential lookup, file creation, DB initialization or writes.

See docs/QUOTE_BUNDLE_STAGING.md before execution. Filesystem, DB domain commit and
final audit are NOT atomic together. File-link success + DB failure leaves an
orphan for review, not a file to delete/adopt automatically. A successful fresh
retry cannot repair an older nonterminal audit job. No PUBLISHED event is used.

## Safe apply and mandatory QA
In C:\Projects\nse_quant_platform inspect git branch --show-current, git log -1 and
git status --short. Require feat/medallion-feature-store, reconcile 2b29bc4 or newer
without resetting work. Copy ONLY seven repository additions. STOP on existing
destination paths and compare rather than overwrite. Run verify-local.ps1 from
extracted bundle. Review untracked files separately from git diff.
No dependencies, architecture, typing rules, configs or existing tests weakened.

## Verification disclosure
40 focused tests passed on Python 3.12.8 with actual DuckDB file-backed transactions
and actual filesystem fsync/hard-link operations. Cases include artifact/metadata
retries, orphan/missing/corrupt evidence, no overwrite/adoption/reseal, rollback,
final-audit failure, interrupt cancellation, root/schema/version/history bounds,
source isolation, Gold catalog ambiguity, default plan and CLI read-only/redaction.
Source assembly is substituted at the staging boundary. Sandbox audit/contracts
were reconstructed from inspected code with condensed formatting/diagnostics;
codec/models used an interface-level harness, not a repeat of all baseline codec
validation. These harness dependencies are NOT delivered. Repository tests import
the actual committed codec/audit/models and existing codec tests remain unchanged.
This is not full source-to-publication or crash/power-loss verification. Full
required repository tests, Ruff and mypy were not run here; local QA mandatory.
Python line-length, staged patch whitespace and ZIP/file checksums were verified.

Suggested commit after local QA:
feat(data-platform): stage audited immutable quote-feature bundle artifacts

Loading and migration remain on hold until the platform acceptance gates pass.
