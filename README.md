# Verified staged quote-feature bundle consumer

## Baseline / inspected interfaces
User baseline 7d340d4, QA/tests passed and HEAD/origin aligned by provided Git log.
Local branch/HEAD cannot be independently accessed. This turn inspected actual
quote_bundle_staging.py exact schema/root/scope/config/contract, feature_bundle.py,
quote_bundle_assembly.py, shared reference_supersession.py and bundle tests/docs.
A targeted BundleArtifacts source lookup failed; its read_exact/root/exists API
is grounded in the current staging source calls and prior committed delivery.
No existing source, codec, artifact helper, staging service or tests overwritten.

## Add only
src/nse_quant/data_platform/quote_bundle_stage_reader.py
tests/data_platform/test_quote_bundle_stage_reader.py
docs/QUOTE_BUNDLE_STAGE_CONSUMPTION.md

## Public service
read_staged_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold,
    staging, bundle_id=<exact lowercase SHA256>, artifact_root=Path(...))

Caller-owned read-only connections, file-backed separate staging metadata, no
outer transactions. Returns immutable StagedQuoteBundleEvidence. No new CLI is
needed for this service increment. No source acquisition, migration or publication.

Checks dedicated/root/schema/contract/version constraints, invalidation-first
complete history, all linked attempt audits and first job, exact bounded artifact
bytes/content/counts/scope, fresh native assembly, then observed metadata/file
stability again. No artifact/metadata/audit writes, initialization or repair.
Expected evidence failures return bounded blocked reasons with no bundle. Invalid
pins/configurations and operational failures raise. verified_current still means
SEALED_NOT_PUBLISHED evidence, not temporal admission or decision eligibility.
See docs/QUOTE_BUNDLE_STAGE_CONSUMPTION.md for exact policy and limits.

## Mandatory local QA / apply
Inspect git branch --show-current, git log -1 and git status --short in
C:\Projects\nse_quant_platform. Require feat/medallion-feature-store; reconcile
7d340d4 or newer without resetting. Compare local staging/codec/assembly interfaces.
Copy only the three additions. STOP on existing paths and compare rather than
overwrite. Run verify-local.ps1 from extracted bundle. Review untracked additions
as well as git diff. No deps, typing rules, existing tests or architecture weakened.

## Verification honestly performed
48 focused tests passed under Python 3.12.8 with actual file-backed DuckDB read
snapshots and filesystem artifact reads. Tests include root/contract/audit/scope/
version checks, failed-successor invalidation, ambiguity/graph errors, incomplete
retry obligations, orphan/missing/corrupt artifacts, size/history limits, current
source rejection/drift, final metadata/artifact drift and unchanged read-only DB/
artifact hashes (including a metadata catalog named gold).
Fixtures are schema replicas, not the production staging writer. Source assembly
is substituted. Sandbox baseline graph code/models/constants and an interface-level
codec/artifact-reader harness were materialized; these harness dependencies are
NOT shipped. Repository tests import actual committed dependencies and baseline
codec tests remain unchanged. No full writer-to-source, publication or crash pass
is claimed. Full repository suites, Ruff and mypy were NOT run here; local QA needed.
Python line lengths, static unused-import scan, staged patch whitespace, ZIP
integrity and per-file hashes were checked; these are not substitutes for Ruff/mypy.

Suggested commit after all local checks:
feat(data-platform): verify staged quote bundles against audits and current sources

Data loading/migration remain deferred. Reviewed recovery planning and separately
authorized publication/temporal admission are further acceptance stages.
