# Research-IV immutable artifact materialization (not audited staging)

## Baseline and selected scope

User reports 64ec9b6 at local HEAD and origin/feat/medallion-feature-store with QA
and tests passed. This closes the inspection fixture failure. Uploaded current
sources include that repair. No committed fixture or prior source is overwritten.
Direct repository writes are unavailable; no staging/commit/push is performed.

Actual sources inspected: research bundle archive/record interfaces and current
revalidation; quote staging/reader/artifact implementation; native bundle codec;
native audit/contract foundations; repaired inspection and current boundary fixtures;
pyproject.toml. The quote artifact format and all existing APIs remain untouched.

Selected bounded slice: real immutable research-IV artifact file materialization,
a prerequisite for a NEW dedicated audited research staging transaction. This is
NOT that transaction. It intentionally introduces no domain table, registration,
audit write, seal/admission record, publication format or accepted staged state.

## APIs

- research-iv-artifact-files@1: ResearchIvArtifactFiles(root)
- native-research-iv-artifact-materialization@1: materialize_research_iv_artifact(...)

The native API accepts the seven existing database handles used by bundle
revalidation, and exact keyword pins:

```python
materialize_research_iv_artifact(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, bundle_archive,
    build_id_pin=reviewed_bundle_archive_record_id,
    expected_archive_fingerprint=reviewed_bundle_archive_fingerprint,
    expected_bundle_id=reviewed_feature_bundle_id,
    expected_revalidation_fingerprint=reviewed_current_revalidation_fingerprint,
    artifact_root=absolute_dedicated_trusted_path,
    initialize=False,
)
```

There is NO caller verified/result/bundle DTO and NO auto-filled/latest reviewed
pin. expected_revalidation_fingerprint comes from an explicitly reviewed observation,
not from self-hashing a caller document. The service freshly calls the ACTUAL current
bundle revalidator before writing and again after writing. Each current revalidation
already performs its own two native whole-set assemblies. Fresh runtime/metadata or
archive history changes require explicit new review, never tolerance/rounding.

Before-result mismatch returns review_required without creating the root or file.
A positive before-result must reproduce all reviewed pins and narrow positive
flags while retaining all authority/eligibility denials. Exact canonical feature
bundle bytes are extracted from the fresh observation and verified by the actual
research bundle codec. No pricing kernel, legacy adapter or source fixture is
substituted by production code.

Root must be absolute, unambiguous, dedicated, trusted and separate from every
supplied database (including attached database paths), not its parent/child.
Existing root contents are bounded/checked; hardlinks from entries to input
files are rejected. Native revalidation retains its own database alias protections.

## File behavior and explicit initialization

A file is named `<exact bundle_id>.research-iv.json`. bundle_id is SHA-256 of the
existing canonical research-IV bundle manifest bytes. The existing quote .json
format/store is NOT reused or extended.

The low-level file API accepts ONLY immutable nonempty bytes <=4 MiB with an exact
SHA-256 pin. It deliberately checks bytes/hash, NOT native source/math/schema truth.
Tests with arbitrary synthetic pinned bytes prove only filesystem integrity.
The native API additionally applies the actual research bundle codec.

initialize=True creates only the explicitly NEW root, after the fresh native
before-observation matches. It never creates missing ancestors or adopts an
existing directory. initialize=False requires an existing dedicated root. Existing
final files are NEVER overwritten or silently adopted, even if bytes match and a
fresh native observation matches. No implicit exact-retry acceptance is claimed.

Writing uses a private tempfile, complete write/flush/fsync, then os.link to the
final name WITHOUT replacement. There is no rename/copy fallback. Only the private
temporary file is cleaned up by this call. An existing final file remains unchanged.
Read uses bounded bytes/hash, regular-file and opened inode checks. Root symlink/
junction redirections and unexpected files/directories/pending remnants require
review. A root supports at most 256 final entries; no unbounded recursive scan.
No automatic final artifact deletion, pending-remnant cleanup or repair is supplied.

## Non-transactional boundary and orphans

A final hardlink can exist even if a subsequent operation raises. The final artifact
is NEVER removed in that failure handler. A failed temp cleanup can also leave a
pending file; later operations block for review instead of deleting it.
File fsync is NOT a directory-fsync, crash-durability or multi-resource atomicity
guarantee. The trusted single-owner directory must support same-filesystem hardlinks.
Windows/NTFS support and filesystem failure behavior require actual local QA.
Path preflight/inode checks are NOT protection from a privileged/concurrent hostile
writer, root replacement, whole-file rollback or external mutation through hardlinks.

After writing, an ACTUAL second current-native revalidation must match the full
before DTO, followed by an exact file reread. If the after-result is negative or
changed, return review_required with BOTH observations and artifact_written=True.
Unexpected exceptions propagate without an accepted return. In either case a
visible unbound final artifact can remain: retain for explicit review, never adopt
or silently retry it. This package supplies no orphan recovery/decision plan.

Even the narrow successful status is deliberately:
`materialized_research_iv_artifact_not_staged`.

The receipt carries both observations, exact expected pins, artifact name and byte
recheck flag. audited_stage_recorded ALWAYS remains false. Publication, identity,
availability, economic validity, acquisition authenticity, model suitability,
authoritative terms, atomicity and eligibility remain false/None. Generic event_ts
and published_at remain None. In-memory observations are NOT durable audited seals.

ALL artifacts from this package remain unbound until a future distinct audited
staging contract explicitly binds/revalidates them. Existing file presence, a hash,
actor name, native positive, or later good result is not stage acceptance.

## Additive application and QA

Eight new payloads; check each destination before copying. Do not overwrite existing
local/committed content. Python >=3.12, SciPy >=1.14.0, cryptography >=46.0.0 and the
actual project Ruff/mypy configuration are unchanged. No dependency harness/replica,
weakened test, assertion, bound or numerical tolerance is supplied.

The Windows runner scripts/qa/qa_research_iv_artifacts.ps1 requires -ExpectedHead
with the reviewed FULL 40-character local Git hash. Inspect git status/diff and
`git rev-parse HEAD` first. This value is NOT a filename, short 64ec9b6, reviewed
archive fingerprint or ZIP checksum. The runner verifies branch, exact HEAD,
ancestry from 64ec9b6 and payload checksums; prints uv's actual interpreter and
installed dependency versions; runs focused and all mandatory QA:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It also lints the ZIP verifier and checks untracked delivered whitespace. No Git
stage/commit/push, dependency change, log discard or native data loading is done.
The separate Python ZIP verifier instead takes an archive path and --sha256 with
the supplied 64-character ZIP checksum. Its manifest covers eight payloads excluding
itself; full archive checksum covers everything including the manifest. Integrity
relative to a supplied hash is not authenticated publisher authority.

## Acceptance gates retained

See the separate verification report. Supplied native boundary tests use existing
actual Gold/archive/audit/model fixtures with LOWER SOURCE KERNEL SUBSTITUTED.
They are not full native acquisition-to-materialization E2E, and are not claimed run.
No new execution CLI or automatic user-data loading is introduced. No acquisition,
user migration/backfill, real key/identity/policy/authority registration, production
publication, trading or decision cutover occurs. Passing this package's QA does
not complete audited staging, eligible admission, decisions, replay or the platform.
