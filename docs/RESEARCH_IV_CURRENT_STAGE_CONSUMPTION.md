# Read-only current-source consumption of an audited research-IV first stage

## Source reconciliation and baseline

Updated sources now returned the ACTUAL research_iv_first_stage.py,
research_iv_stage_record.py and test_research_iv_first_stage_boundary.py. The prior
source-access blocker is closed. Their real typed reader, stored four-pin ordering,
whole-store audit behavior, full-observation digest formula and fixture tuple were
inspected and reconciled with bundle revalidation and pyproject. No stale generated
stage implementation is substituted or overwritten.

Latest explicit user-confirmed HEAD/origin and QA-passed baseline is 9fffc70. No
newer commit/QA result was supplied. The previously delivered independent inventory
package remains locally QA/commit UNCONFIRMED and is NOT a dependency here. Upload
presence alone is not evidence of a new commit or successful QA.

Direct repository writes are unavailable. Eight additive payloads are supplied;
no staging, commit, push, runtime source overwrite or dependency change occurred.
Check every destination before copying; reconcile any existing local/tracked path.

## API and accepted scope

- research-iv-current-stage-observation@1
- research-iv-first-stage-current-source-revalidation@1

```python
revalidate_research_iv_first_stage(
    bronze, frame_silver, reference_silver, assessments,
    source_gold, archive, bundle_archive, staging,
    stage_build_id_pin=reviewed_stage_build_id,
    expected_stage_fingerprint=reviewed_stage_recording_fingerprint,
    artifact_root=exact_recorded_absolute_root,
)
```

There are EIGHT caller-owned existing database handles. staging is the dedicated
first-stage database, archive is individual IV builds, bundle_archive is bundle
recordings. Source roles may share supported handles; staging cannot alias any
input, including a distinct cursor on the same live file or attached file aliases.
Existing underlying bundle/member archive alias protections remain unchanged.
Artifact root cannot overlap any database path or contain an entry hardlinked to
one. Trusted single-owner handles/root required, no outer/shared writer transaction.

stage_build_id_pin is the STAGE BINDING ID, not a bundle archive ID, member ID or
feature bundle ID. expected_stage_fingerprint is the explicitly reviewed FULL
stage-recording evidence fingerprint from the ACTUAL read_research_iv_first_stage.
Never auto-fill it from latest state at execution. The caller supplies no bundle,
result, membership or verified DTO, and cannot choose replacement source pins.
No new CLI is introduced, and imports do no path probing/execution imports.

## Invalidation-first execution

1. Gate actual store/record/codec/file/revalidation versions and known bounds.
2. Validate exact reviewed stage pins and database/artifact separation.
3. Invoke the ACTUAL first-stage reader. It checks whole store, original contract,
   linked origin/attempt, failed/incomplete/unlinked obligations and exact artifact.
   Require the exact reviewed ID and fingerprint before any native pricing call.
4. Decode and verify the frozen binding bytes, root and ID. Reconstruct all four
   original pins (bundle archive record, archive fingerprint, feature bundle ID,
   original native revalidation fingerprint) only from the verified binding.
5. Read exact artifact bytes. Invoke the ACTUAL bundle revalidator TWICE. Each
   invocation already performs two whole-set native forward/reverse assemblies.
6. Compare full canonical current-native DTO bytes with each other, and their
   SHA-256 values against BOTH original recorded before/after digests. Require
   typed positive native observations, exact four pins and all original denials.
7. Read the artifact again and compare ACTUAL canonical bundle bytes from BOTH
   assemblies of EACH native observation against both artifact observations.
8. Invoke the full first-stage reader again and require an unchanged COMPLETE DTO
   including stage/audit/artifact fingerprint. No metadata-only/IV-only/latest pin
   fallback, rounding, tolerance or acceptance of a later-good observation.

Known designated stage-review failure after native calls retains both actual
native observations and byte/digest comparison in a review result. Unexpected
codec/database/filesystem/native exceptions propagate with NO accepted partial
return. Every exception means no usable observation, never cached/old-good fallback.
A changed bundle archive audit fingerprint is NOT silently refreshed. The original
one-binding/no-retry/no-adoption stage contract remains untouched.

## What is and is not reproduced

The actual binding retains hashes of complete native DTOs, not their original
full bytes. This consumer therefore claims matching FROZEN NATIVE DIGESTS, not
byte-for-byte replay of retained original native DTO bytes that do not exist.
Current native DTO bytes are directly compared to each other; current bundle
manifest bytes are directly compared against actual artifact reads. Stage-record
integrity is verified by actual store/audit/codec APIs, not a caller self-hash.

Positive status: matched_current_research_iv_stage. Narrow flags:

- archived_stage_recording_verified
- current_source_checked
- recorded_native_digests_matched
- artifact_bytes_matched
- stage_unchanged_observed

Only positive returns expose accepted bundle_id and evidence_fingerprint. Review
returns retain available before/after stage/native facts but accepted IDs stay None.
The evidence fingerprint binds reviewed stage pin/fingerprint, exact canonical
stage DTO hashes, byte-comparison evidence and bundle ID. It is in memory only.

ALL publication, identity, availability, historical validity, authoritative terms,
model suitability, acquisition authenticity, atomicity and eligibility flags remain
false/None. event_ts and published_at stay None; no common economic clock inferred.
This is a current RESEARCH observation, not eligible admission, publication, a new
stage/audit write, trading authority, complete replay or global latest state.

## Resource and temporal bounds

Each encoded complete native bundle-revalidation DTO is capped at 160 MiB. The
existing profile can include two <=24 MiB archive result strings (escaped again in
outer JSON), two <=24 MiB fresh results and bounded metadata, so this outer DTO
needs a larger bound than its nested assembly. Two such compared payloads total
<=320 MiB; four bundle encodings/reads remain individually <=4 MiB. These are payload
bounds, NOT a process-memory ceiling: dataclasses/strings/JSON copies add memory.
A resource exception cannot produce accepted prefix output.

All original per-member/pass/archive bounds, numerical tolerances, Python/SciPy/
cryptography minimums and project QA settings remain unchanged. Actual retained
stage profile still caps record JSON at 8 KiB and checks the entire dedicated store.

Repeated observations do not establish a cross-database/file atomic snapshot,
continued validity after return, hostile-writer security, rollback protection,
namespace authority, canonical identity or economic/availability evidence. A
changed runtime/metadata fingerprint may require explicit new review/reassessment,
not mutation of the original stage. No retry/adoption or automatic repair is added.

## Local application and QA

Run scripts/qa/qa_research_iv_current_stage.ps1 with -ExpectedHead set to the reviewed
FULL 40-character local Git HEAD from git rev-parse HEAD after actual status/diff/
branch review. It is NOT short 9fffc70, a Python filename, stage fingerprint or ZIP
checksum. The runner checks branch/HEAD/ancestry, delivered hashes, uv's actual
interpreter and unchanged Python >=3.12, SciPy >=1.14.0, cryptography >=46.0.0 bounds;
runs focused tests and ALL mandatory commands:

```powershell
uv run pytest tests/data_platform -q
uv run pytest tests -q
uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
uv run mypy
git diff --check
```

It additionally lints ZIP verifier and checks delivered/untracked whitespace.
No stage/commit/push, fake native dependency harness, dependency downgrade, skipped
test or unrelated-log deletion is performed. The standalone Python verifier instead
takes ZIP path and --sha256 (separate 64-character archive checksum). Manifest hashes
eight payloads excluding itself; full ZIP checksum covers every byte/manifest.
Integrity relative to a pin is not authenticated publisher/source authority.

See the separate verification report. Supplied native boundary cases use ACTUAL
stage/codec/audit/artifact/bundle/model APIs with the existing LOWER SOURCE KERNEL
SUBSTITUTED. They are not full native acquisition E2E. Existing memory fixture
sources remain as designed; no file-backed conversion or identity assertion is
weakened and no inspection repair is replaced.

No acquisition, user data loading/migration/backfill, actual identity/key/policy/
authority registration, production publication, trading or cutover is executed.
Whole-platform eligible admission, decisions, complete exact replay and operational
acceptance remain separate gates after actual local QA of this candidate.
