# Plan-first research-IV bundle inspection

## Baseline and scope

User reports local HEAD 092d936 on feat/medallion-feature-store, with QA/tests
passed. The supplied log still places origin/feat/medallion-feature-store at
c9c6c42. Local commit acceptance is recognized; push is NOT claimed. Uploaded
sources remain snapshots, not independent local HEAD or QA verification.

Inspection covered the actual updated bundle revalidation service and boundary
fixtures, individual IV inspection CLI/tests and pyproject. The uploaded service
has formatting changes from the generated version; no existing source is replaced.
Python >=3.12, SciPy >=1.14.0, cryptography >=46.0.0 and all QA rules remain unchanged.

This additive slice exposes existing current-source revalidation safely for manual
research inspection. It is not another source verifier, archive store, staging
lifecycle, publication/admission format, strategy input, decision loop or replay.
Direct repository writes are unavailable. No staging, commit or push was performed.
Review all eight new paths before copying; stop and reconcile if any already exists.

## Entry points

- scripts/inspect/inspect_research_iv_bundle.py
- python -m nse_quant.data_platform.research_iv_bundle_inspect_cli
- research-iv-bundle-inspection@1

Both call the actual committed revalidate_research_iv_bundle service @1. Neither
reimplements numeric computation or refreshes reviewed pins from current state.

The seven required path options, in native positional role order, are:

1. --bronze-db
2. --frame-silver-db
3. --reference-silver-db
4. --assessment-db
5. --source-gold-db
6. --archive-db (individual IV build archive)
7. --bundle-archive-db (bundle recording archive)

Both --build-id-pin and --archive-fingerprint are mandatory lowercase SHA-256 pins.
The first is the BUNDLE ARCHIVE RECORD build_id, NOT a member build ID or nested
feature bundle_id. The second is the explicitly reviewed full bundle archive
fingerprint, NOT a Git HEAD or ZIP checksum. There is no automatic latest lookup.

## Default: nonexecuting plan

Example using deliberately nonexistent paths and syntactically valid example pins:

```powershell
uv run python scripts/inspect/inspect_research_iv_bundle.py `
  --bronze-db missing-bronze.duckdb `
  --frame-silver-db missing-frame.duckdb `
  --reference-silver-db missing-reference.duckdb `
  --assessment-db missing-assessment.duckdb `
  --source-gold-db missing-gold.duckdb `
  --archive-db missing-member-archive.duckdb `
  --bundle-archive-db missing-bundle-archive.duckdb `
  --build-id-pin ('a' * 64) --archive-fingerprint ('b' * 64)
```

This only prints PLANNED. It does no file/path probing or resolving, opens no
files/databases, imports no execution dependencies, initializes nothing, and
performs no network/credential lookup. Paths are echoed as supplied, not checked.
Each path is a nonempty string <=4096 characters without control characters.
A planned result is NOT evidence that any input exists or any source is valid.

## Explicit execution

Only after independently reviewing the record/fingerprint and seven already-existing
synthetic/approved databases, use their real paths/pins and append --execute.
Do not execute against example pins. User data loading and operational cutover
holds are not lifted by this inspection feature.

Execution checks all seven paths exist and rejects bundle archive aliases to any
input and member archive aliases to any of the first five sources. Same-file checks
also detect hardlinks. Supported source aliases share a single actual read-only
DuckDB connection; no second independent connection to a live alias is opened.
Every connection uses read_only=True, closes on normal/review/error exits, and is
never initialized. A later connect failure closes earlier opened handles.

The actual service version/type is checked, and the committed service performs
archive/source revalidation. All its bounds, full-history audit obligations,
negative-observation preservation and exact byte comparisons remain unchanged.
Filesystem identity checks are preflight, not a cross-process TOCTOU/security
boundary. Run in a controlled single-owner environment; no cross-database atomic
snapshot or protection from privileged file replacement is claimed.

## Output and exit codes

- 0: default PLANNED, OR explicit matched_current_research_iv_bundle. Always inspect
  status; exit 0 from planning is NOT successful source verification.
- 2: explicit service review_required, or argument-parser usage error (stderr).
- 1: execution failure with fixed IV_BUNDLE_INSPECTION_FAILED diagnostic.

Execution prints a bounded <=16 KiB JSON summary. It includes exact reviewed pins,
service/evidence/bundle IDs, reason codes and narrow observation flags. It omits
full archive/member/calculation/assembly payloads and all exception text. The full
in-memory service DTO remains available via the existing programmatic API; the
CLI summary is not a replay artifact or replacement evidence document.

Positive summaries require the actual service result type/version, matching request
pins and all five observation flags true, with publication/authority/eligibility
denials unchanged. Review summaries cannot contain an accepted bundle/evidence ID.
Any malformed projection or failed cleanup is a sanitized execution failure.
No partial success is emitted. Flags about identity, suitability, publication,
availability, historical validity, acquisition authenticity, atomicity and decision
eligibility remain false; canonical_contract_id stays None.

## QA and integrity

Read RESEARCH_IV_BUNDLE_INSPECTION_VERIFICATION.md for executed versus unexecuted
checks. The PowerShell runner requires the full 40-character local Git HEAD from
`git rev-parse HEAD`, explicitly reviewed with actual branch/status/diff. ExpectedHead
is NOT a Python filename, 7-character commit, archive fingerprint or ZIP SHA-256.
It checks branch/HEAD, ancestry from 092d936 (not push state), uv's actual interpreter
and unchanged dependency bounds, then focused and all mandatory QA commands:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It also lints the new archive verifier and checks delivered/untracked whitespace.
It does not auto-stage source, repair failures, install replicas or discard logs.
The separate Python ZIP verifier takes an archive path and --sha256 (64-character
ZIP checksum), NOT ExpectedHead. The per-file manifest covers eight payloads,
excluding itself; the archive checksum covers the full ZIP including the manifest.
Hashes establish integrity relative to a supplied pin, not publisher authority.

Five supplied repository boundary tests reuse actual bundle/archive/revalidation
fixtures with the existing LOWER SOURCE KERNEL SUBSTITUTED. They are not full
native acquisition-to-inspection E2E. The sandbox tests of real DuckDB handles
prove connection behavior on disposable tables, not numerical/source truth.

## Holds

No acquisition, user loading/migration/backfill, real identity/key/policy/authority
registration, production bundle publication, trading or cutover is executed. No
trust root or temporal/identity evidence is manufactured. Local QA of this one
package is not whole-platform acceptance, staging completion or eligible admission.
