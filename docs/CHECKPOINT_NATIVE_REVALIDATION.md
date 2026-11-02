# Checkpoint-pinned native policy revalidation @1

## Reconciliation

Latest USER-REPORTED baseline 1eaef3f on feat/medallion-feature-store and origin,
accompanied by QA/test update. Assistant has no actual repository/branch/HEAD access,
no staging/commit/push or repository QA execution. Inspected current uploaded
policy_checkpoint_store.py, policy_checkpoint_record.py, native_policy_window.py,
and actual current native checkpoint/window tests. Preserve committed fetchone
None assertions and all other fixes: no existing file is included or replaced.
Python >=3.12 and existing dependencies/versions remain unchanged.

## New capability

The writer stores local checkpoints but existing native-window consumption does not
require one. This additive READ-ONLY API requires an explicit reviewed checkpoint ID
AND full scoped checkpoint-history fingerprint, freshly reproduces its recorded
signed window, then ties that retained head to fresh native assertion/proof/policy
observations. It does not accept caller-created checkpoint/native evidence DTOs.
No auto-latest selection or write/repair/initialization is performed.

    revalidate_checkpoint_native_policy(
        checkpoint, registry, bronze, proof_bronze,
        policy_id=..., expected_checkpoint_id=..., expected_history_fingerprint=...,
        recording_query=ScopeQuery(...),
        <native-policy-window receipt inputs>,
        snapshots=..., governance_public_key=..., expected_governance_key_sha256=...,
    )

Unlike native_policy_window, callers do NOT supply anchor/tip: they are taken from
the exact audited retained head. Caller supplies exact ORIGINAL signed snapshots.
No DB/path/network/credential opens; owned existing connections, no outer transaction.
Compatible read-only checkpoint handle supported. Existing native source contracts
still apply to registry/Bronze/proof connections. No new CLI is provided.

## Critical query-interface reconciliation

Existing checkpoint window_fingerprint includes per-query policy assessments.
Therefore the ORIGINAL recording query must be explicitly supplied and fully
validated. It cannot be inferred from the current assertion or a claimed issuer.
Replay uses that query to reproduce the exact stored fingerprint and entire
CheckpointRecord (including predecessor, endpoint pins and denied keys).

Then the ACTUAL native reader independently derives the CURRENT assertion's query
from the typed recorded request and explicit signer pin. The recording query may
have been denied while the current query is permitted; that does not make a valid
checkpoint unrecordable or confer authority on the recording query. No weakening
of exact checkpoint replay to permit query substitution. If original recording
inputs/query are unavailable, this consumer cannot reproduce the checkpoint;
unknowns remain unknown and no synthetic recovery is attempted.

## Read sequence / invalidation

1. Native full checkpoint history/audit read. Require exact reviewed head AND exact
   reviewed complete history fingerprint, not head ID alone. Empty/stale pins block.
2. Actual signed-window replay using original recording query and head endpoints.
3. Reconstruct full CheckpointRecord from actual verified window; exact record and
   checkpoint ID must equal retained head. No caller-claimed fingerprint acceptance.
4. Actual inspect_native_policy_window, including all receipt/source/recording gates.
5. Second actual inspect_native_policy_window, preserving both observations even
   when the first returns review_required. Never pick the earlier good result.
6. Second native full checkpoint history/audit read. Any observed head/history change,
   including exact retry or newly incomplete audit, blocks success.
7. Require both complete native results and full type-tagged observation agreement.

Digest projection handles actual DTO asdict values, including detached proof bytes,
without dumping raw bytes into JSON/logs. Each value type is explicitly tagged;
ordinary JSON mappings cannot impersonate the byte-digest representation. Nonfinite
floats, mutable bytes, nonstring mapping keys and unknown objects reject rather than
being stringified. Fingerprint binds both checkpoint/native views and recording replay.

CheckpointReviewRequired before/after produces redacted fixed review reasons. An
after-failure preserves earlier native results but sets no bound success. Unhandled
SQL/input/native exceptions propagate; never fabricated success. Early pin or replay
failure does not falsely claim later native reads occurred. Version checks explicit.

## Scope of positive result

retained_checkpoint_and_current_native_scope_bound means exact local retained-head
replay and observed native consistency. exact_checkpoint_record_reproduced=True
and retained_head_and_native_scope_bound=True are narrow evidence flags.

policy_currentness_verified, policy_authority_authenticated, issuer_authenticated,
namespace_authority_verified, identity_verified, authorized_revocation_asserted,
availability/historical-validity/decision flags and cross-database atomicity stay
false. Canonical underlying ID remains None. No authoritative namespace/trust root,
issuer ownership, economic/publication eligibility or globally latest policy inferred.

History pins are caller-reviewed local expectations, not authenticated governance.
Whole-store restore/replacement, privileged SQL, independent key rotation and
change-and-revert between sequential reads are not solved. Future continued validity
is not asserted. The existing native reader is not silently replaced or trading
cut over; this is an explicit new consumption API. No checkpoint writes or audit
repair in this service. No reclassification of old evidence or legacy data.

## Tests / delivered verification

24 PURE helper tests passed in sandbox: reviewed-pin exactness, byte-aware/type-tagged
digests, stable mapping order, nonfinite/unsupported-value rejection. They are NOT
native revalidation or E2E. Eleven native cases supplied, NOT run by assistant:
positive exact replay, separate recording/current queries, wrong recording query,
wrong head/history pins, actual retry/advance between checkpoint reads, new incomplete
native audit, actual assertion retry between native observations, obsolete recording,
and read-only checkpoint operation. Actual AuditLedger, checkpoint writer, signed
policy verifier, Bronze/identity native fixtures used locally. Mutation hooks wrap
actual native reads and execute real fixture writes; no fabricated success dependency.

No actual repository tests/QA, full native integration, Ruff, mypy or Windows PowerShell
run here. No dependency replicas, broad ignores, skips or weakened assertions.
Python syntax, line lengths/trailing whitespace, ZIP CRC/exact seven-member set,
six payload checksums and archive SHA256 verified.

Review/copy absent additions; if a target exists, stop/compare before any overwrite.
Run .\scripts\qa\qa_checkpoint_native_revalidation.ps1. It verifies expected
branch, actual HEAD/1eaef3f ancestry/status/runtime/dependency version; runs focused
and mandatory QA, stopping at first failure, with no staging/commit:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Untracked files not covered by git diff --check; payload whitespace checked separately.
Preserve unrelated logs. Suggested commit ONLY after actual local passing QA:
feat(data-platform): revalidate native policy evidence against exact retained checkpoints

No acquisition, real identity/key/policy/checkpoint registrations, user-data loading,
migration, backfill, publication, trading or decision-loop cutover performed.
Synthetic disposable fixtures only. Full platform acceptance/loading hold unchanged.
