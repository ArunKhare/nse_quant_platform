# Native storage support for signed delegation references @1

## Merge/source reconciliation

User-reported QA/test-passed HEAD 9ed3f16, merge of feat/medallion-feature-store,
local/origin aligned; c776d9b is reported delegation-review feature commit.
No assistant repository access or independent HEAD/parents/merge inspection.
The user-provided GitHub URL fetch failed; no public repository content obtained.
Actual uploaded delegation_review.py, delegation_native_reader.py, native tests,
bronze_jsonl_support_reader.py and checkpoint_observation.py were inspected.
Current contracts match new calls. Merge changes cannot be inferred from snapshots.
No existing source/test/schema/dependency replaced; stop/compare if target exists.
Python >=3.12 preserved. No staged/committed/pushed changes by assistant.

## Concrete new boundary

Existing delegation evidence_refs were signed claims only. This new native consumer
requires exact coverage of ALL signed reference slots and invokes the actual native
Bronze+audit+JSONL derivation consumer on every unique pin/plan before AND after
fresh native delegation observations. Valid approval signatures cannot compensate
for a nonexistent or changed fragment, missing audit or unsupported source profile.
This is source-storage LINKAGE, not authority/meaning or another name for approval.

APIs:

    DelegationReferenceSource(
        bronze=<owned existing connection>, support=BronzeSupportPin(...),
        original_plan=<exact original canonical bytes>, expected_plan_sha256=...,
    )
    inspect_delegation_reference_support(
        <same connections/arguments as inspect_delegation_native_binding>,
        reference_sources=(DelegationReferenceSource(...), ...),
    )

No caller-created evidence DTO, source discovery, path/key lookup, I/O opens,
network/credentials, writes, initialization, schema changes or default CLI.
The original native contracts apply to all connections: dedicated file-backed
sources, owned handles, no outer transactions/concurrent writers. Multiple refs may
use one connection and one actual event with different exact original-byte spans.
No live second-instance ATTACH is created or required.

## Exact coverage and bounded projection

1. Actual whole declaration-set schema/signature/model/target assessment FIRST.
   Derive target from typed assertion request and exact policy/key/checkpoint pins.
   Conflicts/disputes/external claims stop with no reference/native reads claimed.
2. Project evidence_refs from original signed bytes ONLY after whole set verified.
   Revalidate each with actual native BronzeSupportPin, not a duplicate implementation.
3. Compute deterministic reference keys from ALL SIX exact support fields.
4. Require one explicit source/plan binding for every DISTINCT reference key.
   Repeated signed slots retained with coverage indices; no missing, unsigned extra,
   duplicate/ambiguous source bindings or first/last source choice. Ambiguous slots
   use -1, never select a source even in diagnostics. Coverage checked before source I/O.
5. Actual inspect_jsonl_bronze_support for ALL reviewed bindings, preserving all
   returned failures. If any incomplete, no native delegation success is attempted.
6. Two ACTUAL inspect_delegation_native_binding calls; preserve both returned results.
7. Actual source checks for ALL bindings again. Require complete sources and exact
   full source/native observation agreement; any observed retry/history change blocks.

<=8 declarations x <=8 references = <=64 signed slots, <=64 unique source bindings.
Immutable tuples only; each original plan 1..65536 bytes, <=4MiB aggregate. Existing
native payload/event/artifact/batch/audit bounds are not loosened. Sources obey the
explicit existing fresh conflict-free JSONL profile, not generic/mixed parser claims.
Caller plans must be the original plans with independently reviewed exact pins.

Native source verification includes actual receipt variants, exact payload and
fragment hash/span, retained input artifact, fresh-batch membership, original audit
and whole scoped obligations, actual DatasetContract, independent strict JSONL
recomputation/order and original-plan/native-input metadata binding. It does NOT
interpret an arbitrary fragment as evidence of reviewer identity or delegation.
No fake format detection or historical payload relabeling.

## Results and limits

New positive status signed_delegation_references_storage_linked sets ONLY
all_signed_reference_storage_verified=True. It means all literal signed ref pins
passed CURRENT native storage/derivation support checks, bracketing two native
internal-review/checkpoint observations. Fingerprint includes coverage/order, exact
support/plan pins, original review evidence, and both source/native observations.
Type-tagged existing observation_digest handles raw detached proof bytes safely.

Old nested supporting_bronze_refs_checked flags remain FALSE in their original
DTOs; this package never mutates/relabels them. The NEW outer flag states the narrow
additional gate. reference_content_semantics_verified remains FALSE: a correctly
stored document or fragment need not demonstrate authority, legitimate approvals
or even relevant meaning. No external source authenticity, distinct humans,
reviewer/organization identity, operative internal authorization, namespace/issuer/
identity truth, revocation or decision eligibility is established. Canonical ID None.

Raw approval declaration and reviewer proofs remain supplied immutable inputs; this
package does not prove THEIR receipt/audit provenance or authenticated approver-key
registration. Reference source provenance here is native platform recording evidence,
not independently authenticated acquisition. External model remains blocked before
storage reads; storage cannot elevate external claims. No real roots are seeded.
No completeness claim for declarations beyond the supplied set.

All observations are sequential, NOT an atomic multi-database snapshot or proof
against change-and-revert. No future continued validity is promised. Missing/extra
coverage, incomplete source or native evidence, or changed observations returns
review_required. Raw SQL/input/native exceptions propagate with no fabricated
success or business rejection; no arbitrary exception bodies/payloads/plans are
added to diagnostics. A raised source error stops execution; later checks are not
falsely claimed. There is no old-good fallback, repair or data admission/cutover.

## Tests and QA honesty

16 PURE coverage tests passed in sandbox. They test real planning code only,
NOT cryptographic/native/storage/E2E verification. Nine native cases supplied but
NOT run by assistant: multiple exact spans/old-flag preservation; missing/extra/
ambiguous coverage before I/O; wrong fragment despite good signatures; actual source
retry drift; incomplete actual audit; external failclosed; source error propagation.
They reuse actual existing checkpoint/identity/proof fixtures, actual native readers,
AuditLedger and real review signatures. Supporting synthetic fragments can be part
of the synthetic statement itself: that demonstrates storage checks, not independent
organizational evidence. Failure/mutation hooks never simulate native success.

No actual repository/native integration/full QA, Ruff, mypy or PowerShell executed.
No native dependency replicas, broad ignores, skips or weakened assertions.
All Python syntax/line lengths/trailing whitespace checked; ZIP nonempty/CRC/exact
seven-member set and six payload SHA256s verified; archive checksum rechecked.

Review/copy ABSENT additions. Then:

    .\scripts\qa\qa_delegation_support.ps1

Runner verifies expected branch, actual HEAD/parents/status and ancestry of BOTH
9ed3f16 and c776d9b. Prints runtime/checks dependency version; runs focused tests
then mandatory QA (fail-fast, no staging/commit):

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Untracked file whitespace checked independently, not by git diff --check.
Preserve unrelated logs. Suggested commit ONLY after actual passing local QA:
feat(data-platform): verify native storage support for all signed delegation references

No live acquisition/loading/migration/backfills/real registrations/publication/trading/
cutover. Independently authenticated governance and authority remain open gates.
Passing this package is NOT platform completion; data-loading hold unchanged.
