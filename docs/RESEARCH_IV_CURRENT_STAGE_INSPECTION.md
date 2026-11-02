# Plan-first read-only current-stage inspection

## Source/acceptance reconciliation

Latest explicit user-reported accepted HEAD/origin with QA/tests passed remains
9fffc70. The current-stage consumer is now present in updated sources with local
formatting/SIM consolidation, but NO newer commit or local QA confirmation was
supplied after its delivery. This package does NOT invent such acceptance or a
failure. The previous independent inventory package is not a dependency.

Inspected ACTUAL current consumer/DTO, current-stage fixture, bundle inspection,
repaired snapshot/handle-rebinding helper and pyproject. No existing code or repair
is overwritten. Eight additive payloads; check each destination before copying and
stop/reconcile if it already exists. No direct repository writes, stage/commit/push.

This slice exposes the ACTUAL current-stage consumer via a bounded diagnostic CLI,
not another analytical/verification implementation. The consumer dependency is
explicitly VERSION-GATED to research-iv-first-stage-current-source-revalidation@1;
the QA runner tests that still-unconfirmed package FIRST, then these new tests and
all mandatory QA. Upload presence is not repository or supported native acceptance.

## Entry points and exact inputs

- scripts/inspect/inspect_research_iv_current_stage.py
- python -m nse_quant.data_platform.research_iv_current_stage_cli
- research-iv-current-stage-inspection@1

Eight required database path options in actual service positional order:

1. --bronze-db
2. --frame-silver-db
3. --reference-silver-db
4. --assessment-db
5. --source-gold-db
6. --archive-db (individual IV archive)
7. --bundle-archive-db
8. --staging-db (audited first-stage store)

Also required: --artifact-root, --stage-build-id-pin, --stage-fingerprint.
The first pin is the STAGE binding ID, not member/build-archive/feature-bundle ID.
The fingerprint is the explicitly reviewed stage-recording evidence fingerprint,
NOT a Git commit, ZIP checksum or native revalidation fingerprint. No latest lookup
or automatic fingerprint fill is supplied. Existing underlying consumer reconstructs
source pins from actual verified stage bytes, not caller DTOs.

## Default nonexecuting plan

Without --execute: PLANNED, no path probes/resolving, file/DB opening, initialization,
execution imports, network or credential lookup. Database path strings <=4096
characters; artifact-root string <=2048; control characters/empty strings rejected.
Paths are echoed as supplied, not verified or silently normalized.

```powershell
uv run python scripts/inspect/inspect_research_iv_current_stage.py `
  --bronze-db missing-bronze.duckdb `
  --frame-silver-db missing-frame.duckdb `
  --reference-silver-db missing-reference.duckdb `
  --assessment-db missing-assessment.duckdb `
  --source-gold-db missing-gold.duckdb `
  --archive-db missing-member-archive.duckdb `
  --bundle-archive-db missing-bundle-archive.duckdb `
  --staging-db missing-stage.duckdb `
  --artifact-root missing-artifacts `
  --stage-build-id-pin ('a' * 64) --stage-fingerprint ('b' * 64)
```

This example only plans. Its dummy pins are NOT reviewed source evidence.

## Explicit execution

Only with real reviewed pins, eight already-existing files and the exact recorded
absolute existing artifact root should --execute be supplied. All DB connections
are opened read_only=True. No write/create fallback for missing input is possible.

Supported same-physical-file aliases among first five sources share ONE connection.
Member archive is separate from those five; bundle archive is separate from first
six; staging is separate from all preceding seven. samefile checks include hardlinks.
Root redirects/junctions, missing/relative/ambiguous roots and DB/root path overlap
are rejected before DB connections. The actual consumer retains further artifact
content/hardlink, whole-stage-audit and source-alias checks. No checks are weakened.

Opened connections close on normal, review and exception paths, including a later
corrupt DB failing to open. No second live instance is opened merely for an alias.
Root text is not replaced with a resolved path for the actual pin comparison.
Controlled single-owner roots/handles required; preflight/repeated observations
are not a hostile-writer or cross-resource atomic snapshot guarantee.

## Diagnostic contract

Exit 0: PLANNED or matched_current_research_iv_stage. Always inspect status: plan
success is NOT native source verification. Exit 2: service review_required, or
parser usage error on stderr. Exit 1: fixed sanitized IV_CURRENT_STAGE_INSPECTION_FAILED.
No exception body, credentials, payload/assembly/calculation/archive JSON or replay
blob is printed. Result summary <=16 KiB; over-budget output fails, never truncates.

Execution checks actual service version and exact result type. It checks requested
pins and strict boolean observation/denial fields; positive requires all five
narrow positive flags plus exact bundle/evidence IDs. Reviews may retain valid
partial observation facts (e.g. native checked but later stage audit failed), but
accepted bundle_id/evidence_fingerprint must remain None. It never chooses a prior
positive over a review. Summary is diagnostic projection, not durable replay,
publication, admission or replacement for the full programmatic observation DTO.

Identity, acquisition authenticity, suitability, availability, historical validity,
authoritative terms, atomicity and decision eligibility remain false/None.
Generic event_ts/published_at stay None. Native frozen hashes are not relabeled as
retained original full replay bytes. No common economic clock is invented.

## Correct fixture boundaries and QA

Five supplied repository CLI cases reuse the inspected seven-role memory-snapshot
helper UNMODIFIED for original sources/Gold/member/bundle archives, then close and
reopen the real stage file as the eighth role. In-memory fixture connections are
NOT assumed to have physical file paths. The test-local adapter rebinds original
four source expectations to the ACTUAL readonly handles only during execution and
restores them in finally. The original exact handle assertion and source substitute
remain unchanged. No native successful computation/model/result is mocked.

These tests are still existing LOWER SOURCE KERNEL SUBSTITUTED boundary integration,
NOT full native acquisition-to-inspection E2E. They were NOT run in the delivery
sandbox. See separate verification report for executed tests and all limitations.

Run scripts/qa/qa_research_iv_current_stage_inspection.ps1 with -ExpectedHead set
to the explicitly reviewed FULL 40-character local HEAD from git rev-parse HEAD,
after branch/status/diff review. It is NOT short 9fffc70, a filename, stage fingerprint
or ZIP checksum. Runner verifies actual branch/HEAD/ancestry, delivered hashes and
uv's actual interpreter/unchanged Python >=3.12, SciPy >=1.14.0, cryptography >=46.0.0.
It closes prior consumer tests FIRST, then focused and all mandatory QA:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It also lints new ZIP verifier and checks delivered/untracked whitespace. No skips,
weakened assertions/tolerances, dependency changes/replicas, log deletion, staging,
commit/push or automatic source repair. The standalone ZIP verifier instead takes
an archive path plus --sha256 (separate 64-character ZIP hash). Payload manifest
excludes itself; archive hash covers every ZIP byte including manifest. Hash
integrity relative to a pin does not authenticate a publisher or native source.

This package completes neither prior consumer acceptance nor staging lifecycle,
eligible admission, publication, decisions, exact replay or whole-platform acceptance.
No live acquisition, user loading/migration/backfill, actual authority/key/policy/
identity registration, production publication, trading or cutover is performed.
