# Bounded native research-IV bundle candidates @1

## Source/commit reconciliation

Latest USER-REPORTED committed QA-passed HEAD33e5484 on
feat/medallion-feature-store and origin, following dd9351c. No assistant local
repository/branch/HEAD proof, staging, commit or push. Actual updated
research_iv_revalidation.py, research_iv_store.py, research_iv_record.py,
research_option_model.py, native_research_option.py and boundary fixture were
returned/inspected. Current public result/calculation/scenario fields reconciled.
Prior quote feature_bundle.py is QUOTE-ONLY; it is NOT replaced/extended/relabelled.
All additions absent-only. Stop/compare if a target exists, preserve committed fixes.
Python>=3.12/SciPy>=1.14 and all dependencies/assertions/model bounds unchanged.
Do not infer uv's interpreter from Anaconda/prompt labels; QA runner prints actual uv runtime.

## New coherent capability

Single IV builds can be archived/currently revalidated. This package assembles a
bounded immutable collection with canonical content, exact reviewed membership,
model/runtime consistency and WHOLE-SET repeated native checks. No subset selected
by successful status. This is NOT audited bundle persistence, publication/staging,
eligible admission, identity acceptance or complete strategy/decision replay.

## Pure artifact contract

Version research-iv-feature-bundle@1; evidence mode
RESEARCH_IV_SNAPSHOT_NOT_PUBLISHED. 1..64 members, <=16KiB/member,
<=4MiB aggregate canonical manifest. Exactly typed immutable member tuple, unique
sorted build IDs. All fields/hash/version/flags validate before encoding/decoding.
Duplicate/nonfinite JSON, unknown keys, noncanonical/trailing representation,
mutable bytes, wrong hashes and unsupported versions reject. No prefix salvage.

Member contains:
- exact IV build pin/input scope/definition fingerprint
- exact reviewed archive fingerprint and observed revalidation fingerprint
- ordered option/spot Gold build pins and scenario terms fingerprint
- exact original terms JSON and full model-calculation JSON (including runtime)
- each original source event timestamp, including None

Input scope recomputed with actual record@1 hashing formula. Calculation ID and
terms pin independently recomputed from literal canonical components, not trusted
as supplied labels. Supported scenario field/domain constraints mirror the explicit
actual model@1 contract, without a pricing/solver replica. Finite Greeks/IV/profile
fields and reason/model version required; all identity/authenticity/suitability/
publication/temporal/decision flags stay false/None. Vega/rho retain original
per-1.00 units and theta original365-day model convention; no conversion or rounding.

Do NOT confuse this with numerical/source proof: a self-consistent fabricated
calculation can pass an OFFLINE checksum constructor. Native source/audit/math
verification is only through the actual assembly service. Offline decoding does
not assert installed dependency versions or provenance/currentness. Runtime labels
are evidence context. No hashes, labels or member IDs become canonical identities.

Duplicate exact (option Gold pin, spot Gold pin, terms hash) scopes rejected even
with distinct IV build IDs. This is within-bundle scenario-role deduplication, NOT
authoritative real-world contract identity. Mixed definition fingerprints or mixed
Python/SciPy runtime pairs reject in this @1 profile; no silently assumed compatibility.
Membership fingerprint covers complete ordered member content, and bundle ID hashes
complete manifest (excluding its own ID), including all fixed negative policy flags.
No generic common event_ts invented: None. published_at None. Per-source known UTC
instants/unknown values preserved without timezone relabeling or now/receipt substitution.

APIs:

    make_research_iv_bundle(members: tuple[IvBundleMember, ...])
    encode_research_iv_bundle(bundle) -> bytes
    decode_research_iv_bundle(raw, expected_bundle_id=...) -> ResearchIvBundle

Pure in-memory codec: no path probing, file/DB/network opens, credential lookup or
writes. No file export or new inspection CLI; default no-I/O CLI rule not implicated.

## Native assembly / all-or-nothing observations

    assemble_native_research_iv_bundle(
        bronze, frame_silver, reference_silver, assessments, source_gold, archive,
        requests=(IvBundleRequest(build_id, expected_archive_fingerprint), ...),
    )

Each request has exact reviewed pins, not caller-created verified DTOs. Validate
ALL request shapes/count/uniqueness before DB work. No automatic latest or source
lookup. Sorted FORWARD pass through actual revalidate_research_iv_build for the
WHOLE set, then REVERSE pass for the WHOLE set. Returned evidence stored in sorted
request order. Every negative observation retained; no success filtering or
replacement by later-good members. Source/native exceptions abort with no partial
bundle; unsupported-resource/contract errors also never yield partial success.

Both passes must be complete and per-member FULL result DTOs unchanged, including
all source/definition-origin/audit/history fingerprints, exact archived result and
numerical context. Actual current revalidator itself brackets two computations with
archive checks. No native source/IV solver replica or altered existing reader.
Inherited native profiles are not upgraded into stronger acquisition/authentication
claims. Original native source connection ownership/no outer transactions apply.

Each pass has <=8MiB cumulative encoded observation budget; enforce incrementally
before retaining further members. New output artifact separately obeys4MiB bound.
Requests must satisfy existing native source/Gold/archive alias protections. No
new DB opens, ATTACHs, schema/domain/audit writes, root registrations or repair.

Positive assembled_current_research_iv_bundle sets only all_members_revalidated
on outer observation evidence. Bundle itself remains research/unpublished with
all authority/eligibility flags false. It contains references and compact model
results, NOT complete raw market-source or whole-platform replay inputs. Current
observations are sequential, NOT one atomic cross-database instant, aligned economic
clock, proof against change-and-revert or future validity. Per-member times can
be different or unknown. It does not establish option/underlying/currency identity
or model suitability. Do not feed it to quote-only publication/admission contracts.

## Verification honesty

36 PURE codec/manifest tests passed in sandbox. Fixtures are explicitly SYNTHETIC
self-consistent JSON, NOT numerical/native/audit/source replicas or claimed success.
They prove artifact consistency/rejection and non-escalation, not native model truth.
Cover deterministic order/roundtrip, exact membership/input/calculation/terms pins,
unknown schemas/keys, duplicates/nonfinite JSON, clock preservation, authority flags,
scenario-scope deduplication, mixed runtime/definition rejection and resource bounds.

Eight boundary tests supplied, NOT run by assistant. Use actual prior native
revalidation/archive/AuditLedger/model/Gold SQL fixtures whose LOWER SOURCE KERNEL
IS SUBSTITUTED. Explicitly NOT full native acquisition-to-bundle E2E. Cover real
2-member roundtrip/no writes, deterministic request order, duplicate pre-I/O,
whole-set failure/no partial output, later source change, earlier-bad/later-good,
actual archive retry drift and resource exhaustion. No mocked successful native result.

No actual repository checks, full native/supported SciPy math execution, Ruff, mypy
or Windows PowerShell executed here. All Python syntax/line lengths/trailing whitespace
checked; ZIP nonempty/CRC/exact seven-member set and six payload hashes verified;
archive checksum independently rechecked. No skips/broad ignores/relaxed assertions.

## Apply and QA

Review then copy ABSENT additions only; preserve unrelated logs. Run:

    .\scripts\qa\qa_research_iv_bundles.ps1

Runner verifies expected branch/33e5484 ancestry, prints actual HEAD/parents/status,
uv Python/SciPy/native version and runs focused tests then ALL mandatory QA, fail-fast:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

No staging/commit. Untracked whitespace checked independently, not by git diff --check.
Suggested commit ONLY after actual passing local QA:
feat(data-platform): assemble bounded research IV bundles from revalidated native builds

No live acquisition/loading/migration/backfills, real registrations, publication,
trading or decision-loop cutover performed. No new platform acceptance claimed.
Data-loading/migration hold remains. Next separate substantive step: audited bundle
persistence/staging/current consumption under a new research-only analytics contract,
then authoritative role/identity/time evidence and eligible native decision replay.
