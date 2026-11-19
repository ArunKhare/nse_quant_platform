# Current-source revalidation of archived research-IV bundles

## Status and source reconciliation

The user reports c9c6c42 at HEAD and origin/feat/medallion-feature-store, with QA and
tests passing, for audited immutable research-IV bundle archival. This supersedes
the older delivery documents' unconfirmed-archive status. It is user-reported local
evidence, not a checkout independently inspected by the assistant. No newer commit
or failure is claimed. The current package remains an uncommitted candidate.

Inspection covered the uploaded bundle store/record codec, native assembly, feature
codec, existing per-build revalidation and their actual boundary fixture interfaces.
The updated archive-record tests contain a typing cast correction; this package
does not replace those tests or reconstruct stale earlier versions. Uploaded
pyproject.toml still requires Python >=3.12, SciPy >=1.14.0, cryptography >=46.0.0,
line length 100, and project-wide mypy. All are unchanged.

Direct repository writes are unavailable. Eight additive payloads are supplied.
Before copying, check every destination against current tracked/untracked contents.
If a path already exists, stop and reconcile; do not overwrite a committed fix.
No install, data loading, staging, commit or push is performed by these scripts.

## Implemented slice

- research-iv-bundle-observation@1: bounded immutable byte comparison.
- research-iv-bundle-current-source-revalidation@1: read-only revalidation of an
  exact reviewed archive record against current native whole-set assemblies.

```python
from nse_quant.data_platform.research_iv_bundle_revalidation import (
    revalidate_research_iv_bundle,
)

observation = revalidate_research_iv_bundle(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, bundle_archive,
    build_id_pin=reviewed_bundle_archive_record_id,
    expected_archive_fingerprint=reviewed_bundle_archive_fingerprint,
)
```

`archive` is the individual research-IV build archive; `bundle_archive` is the
separate research-IV bundle recording database. There are seven supplied database
handles. Source roles may share supported source handles, but the bundle archive
must be distinct from all six inputs, including same-file/attached/cursor aliases.
The existing per-member service still enforces member archive/source separation.
No new database is created or opened by this API: callers own existing handles.
There is no new execution CLI and no automatic path probing at module import.

`build_id_pin` is the BUNDLE ARCHIVE RECORD ID returned by the persistence API,
not a member IV build ID or nested feature bundle ID. The expected fingerprint
is the reviewed full bundle-archive-history observation, not a member's reviewed
fingerprint and not a ZIP checksum. Never auto-fill it from latest state at execution.

## Invalidation-first observation sequence

1. Version-gate bundle store/record/native/feature codec APIs and the 24 MiB result
   bound. Reject malformed pins before connection operations.
2. Reject bundle archive aliases to every supplied input before archive/native work.
3. Invoke the real archived reader, which validates requested scope and original
   definition origin audit obligations. Require the exact reviewed retained head
   AND full archive fingerprint. Old successful pins stop before native pricing.
4. Validate frozen request scope and immutable result identity. Recorded review
   heads stop before fresh assembly; they can never be promoted by later good data.
5. Reconstruct ALL requests solely from verified archived request bytes. No caller
   scenario, bundle, membership list, result DTO or latest-member lookup is accepted.
6. Invoke the actual native assembly TWICE. Each invocation already performs a full
   forward pass and then full reverse pass of actual per-member revalidation.
7. Compare the ENTIRE canonical returned assembly bytes against the recorded bytes
   and each other. This includes complete member observations, runtime/metadata,
   source event times (including None), request pins, reasons, and denial flags.
   No IV-only, bundle-ID-only, rounding or tolerance-based acceptance is permitted.
8. Re-read the full bundle archive observation and require unchanged full DTO,
   retained head and history evidence. Even an exact bundle-record retry changes
   audit history and blocks acceptance until explicitly reviewed again.

Both returned native observations survive a known after-read audit invalidation.
Both negative orderings (earlier bad/later good and earlier good/later bad) block.
Actual exceptions/resource exhaustion propagate without any partial accepted
return. Only the store's designated review exception becomes a review observation;
unexpected database/codec/native errors are not hidden. Every exception means NO
usable result: callers must not substitute cached or older good output.

## Result contract and evidence

The only positive status is `matched_current_research_iv_bundle`, requiring all:

- archived_recording_verified
- current_source_checked
- exact_recording_reproduced
- archive_unchanged_observed
- all_members_revalidated

A positive also supplies the nested bundle_id and a deterministic evidence hash.
On review, accepted bundle_id and evidence_fingerprint stay None. The DTO retains
archive_before/after, fresh_before/after and exact byte comparison evidence wherever
observed. It is an in-memory observation, not an audit write or a publication.

The evidence hash is version-tagged and binds exact archive-record pin, reviewed
archive fingerprint, SHA-256 of each canonical full archive DTO, byte comparison
(including SHA-256 of recorded/first/second complete assembly bytes), and bundle ID.
The code compares ACTUAL BYTES, not merely digests. Digests avoid creating another
combined large evidence serialization; they do not assert origin authenticity.

## Bounds and scope limitations

Each compared assembly is immutable nonempty bytes <=24 MiB, matching the current
archive codec's exact result bound. Three compared payloads total at most 72 MiB;
this is a payload bound, NOT a claim of a 72 MiB process-memory ceiling. DTOs, JSON
strings/objects and validation/hash intermediates allocate additional memory.
The retained archive reader's 64 MiB per-scope history budget and native 1..64
member, 8 MiB-per-pass bounds remain untouched. No dependency or tolerance is weakened.

A member archive retry can invalidate the member's frozen reviewed fingerprint,
even without a numeric change. This service never substitutes a newly observed
fingerprint. Explicit new review/reassessment and archival may be needed.
Likewise runtime or metadata differences require explicit reassessment, not rounding.

The archive scope includes exact reviewed membership pins. Revalidation does NOT
claim globally latest state across other scopes, canonical instrument lifecycle
identity, cross-database atomicity, observation after return, or protection against
privileged rewriting/whole-file rollback. Repeated observations are not an atomic
multi-database transaction or a common economic time.

All publication, availability, historical validity, authoritative scenario terms,
model suitability, acquisition authenticity, underlying binding, atomic snapshot
and decision eligibility flags stay false. canonical_contract_id stays None.
No individual unknown source event time is invented or relabeled.

## Local QA and the two different checksum/HEAD inputs

Inspect the actual checkout before application:

```powershell
Set-Location C:\Projects\nse_quant_platform
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
```

`ExpectedHead` means the FULL 40-character LOCAL GIT COMMIT HASH you reviewed.
It is NOT a Python filename, short c9c6c42 hash, archive fingerprint, or ZIP SHA-256.
Run the supplied PowerShell QA runner with that full hash. It checks exact branch,
reviewed HEAD and ancestry from c9c6c42; reports uv's real interpreter/dependency
versions; checks delivered payload hashes; runs new tests and all mandatory QA:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It also lints the new ZIP verifier and checks delivered/untracked whitespace.
A zero exit from that actual local run is required; no local success is inferred
from sandbox tests. The runner does not auto-stage or discard unrelated logs.

The Python ZIP verifier instead takes a ZIP path and `--sha256` with the separate
64-character archive checksum supplied alongside delivery. It does NOT take
ExpectedHead. Both new scripts belong under scripts/qa/; old moved verifier files
are not modified. The manifest hashes eight payloads, excluding itself; the separate
archive checksum covers the complete ZIP, including its manifest. Hashes provide
integrity relative to the supplied pin, not authenticated publisher authority.

## Acceptance and holds

See RESEARCH_IV_BUNDLE_REVALIDATION_VERIFICATION.md for executed/unexecuted checks.
Repository boundary tests reuse actual native assembly, archive/audit/model/Gold
fixtures with the existing LOWER SOURCE KERNEL SUBSTITUTED. They are NOT full native
acquisition-to-revalidation E2E. No numerical solver is replaced by this package.

This is not a staging lifecycle, publication/admission format, eligible decision
contract, audited decision loop, exact replay completion or whole-platform acceptance.
No source acquisition, user data migration/loading/backfill, real identity/key/
policy/authority registration, production publication, trading or cutover is run.
Those holds remain. The next implementation requires explicit local acceptance of
this package, not upload presence alone.
