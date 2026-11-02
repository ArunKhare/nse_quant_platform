# Signed observed-policy window constraints @1

## Reconciliation

User-reported committed QA-passed baseline 7a12a99 on feat/medallion-feature-store
and origin. Assistant has no local repository/HEAD/branch or write access and did
not stage/commit/push. Source lookup returned current receipt/signature modules,
but did NOT return the newly committed statement_scope_policy/native_statement_scope
sources; a focused retrieval failed. Their interfaces are taken from the last
explicitly delivered, now user-reported committed contract, NOT independently
reconciled current source. Runtime version checks and actual local integration QA
remain mandatory. No dependency replicas or reconstructed policy module were used.
All changes additive; if any target exists, STOP and compare before copying.
Python >=3.12, dependencies, existing schemas/committed fixes stay unchanged.

## Capability and honest boundary

The prior service evaluates one signed snapshot. This package detects conflicting
same-sequence snapshots, observed backwards movement, missing sequence labels,
endpoint-pin substitution and deletion of previously observed global key denials
within a bounded caller-supplied window. It also prevents falling back from a
non-permitting tip to an older permitting snapshot.

This is OBSERVED WINDOW VALIDATION, NOT durable rollback prevention. No database
checkpoint is written. Both anchor and tip are explicit caller-supplied exact
PolicyPosition(sequence, policy_sha256) values, not authenticated freshness evidence.
A caller can supply an old internally consistent window/old endpoint pins; currentness
remains false. No latest/current key or policy is automatically selected.

Existing @1 policies have no predecessor hash. Contiguous signed sequence LABELS
are not a publisher-authenticated causal chain or proof that an intermediate policy
was never issued. No complete global history, key ownership or issuer truth follows.
Only supplied observations are assessed. No causal chain is fabricated.

## Pure contracts

PolicyPosition: exact integer sequence 1..2147483647 (bool rejected), lowercase hash.
PolicyWindowEntry: exact series ID, position, immutable <=128 distinct denied keys.
check_policy_window(entries, anchor=..., tip=...): tuple of 1..64 entries, caller
observation order, all validated before constraints. NOT a signature verification
API; never use its result alone as signed evidence.

Constraints:
- same series policy_id throughout; fixed governance key in signed consumer
- first/last positions equal exact caller anchor/tip
- no backwards movement or gaps in distinct observed sequence labels
- same sequence with different policy hashes -> fork/review
- exact consecutive retries preserved and counted, never erased from fingerprint
- inconsistent same-pin projection rejected by pure kernel
- global denied_keys must accumulate; ANY removal -> review under this contract

A new key-reactivation contract would need independent authorization. This package
has none. Denial-removal rejection is a conservative profile constraint, NOT proof
of authenticated revocation. Grant edits and intermediate query non-permission
are allowed; tip must permit the exact query. Signed authority flags stay false.

## Signed and native APIs

    inspect_signed_policy_window(
        snapshots: tuple[SignedPolicyInput, ...],
        governance_public_key=..., expected_governance_key_sha256=...,
        query=ScopeQuery(...), anchor=PolicyPosition(...), tip=PolicyPosition(...),
    )

Each SignedPolicyInput is original policy_bytes, policy_signature, exact expected
policy SHA256. <=64 snapshots, each <=64KiB, <=4MiB aggregate. Actual existing
assess_signed_scope_policy validates signature AND whole document for EVERY input,
including intermediate denying snapshots. Only after successful whole validation
does the consumer project denied_keys. Invalid intermediate signatures/schema raise;
there is no success filtering or selected-prefix salvage. One fixed externally
pinned governance key only; no key rotation/delegation trust inference.

    inspect_native_policy_window(
        <same native receipt inputs as inspect_statement_scope_policy,
         except single-policy inputs>,
        snapshots=..., governance_public_key=...,
        expected_governance_key_sha256=..., anchor=..., tip=...,
    )

Native query derives from typed request and explicit signer pin, not caller DTO.
A failed window returns review_required with no native check claimed. A consistent
signed permitting tip is passed to ACTUAL inspect_statement_scope_policy, which
re-reads native receipt/recording evidence. Its policy result must equal the verified
tip result. An obsolete recording cannot be rescued by consistent policy labels.
Fingerprint binds full signed observations, exact endpoint pins, retry evidence,
signature hashes and native scope fingerprint. Raw bytes/keys never logged.

All policy currentness, governance authority, issuer/namespace/identity/revocation/
decision flags remain false, canonical underlying ID None. No temporal/economic
validity or availability is inferred. No actual policy/key/identity registrations,
acquisition, live loading/migration/backfill/publication/trading/loop cutover.
No database opens/writes, outer transactions, schema initialization or persistence.
Default no-I/O CLI requirement is not implicated: no new CLI is introduced.

## Verification

21 PURE window-kernel tests passed in sandbox. Not cryptographic/native E2E.
Seven signed integration cases and two native integration cases supplied but NOT
run here: actual prior verifier unavailable as an importable sandbox dependency,
and current committed policy sources were not retrieved. Tests exercise real
cryptography and actual existing services locally, not dependency replicas.
Native tests reuse actual source_claim/proof_store fixtures. No skips, weakened
assertions, fabricated harnesses, broad ignores or mocked-success path.

Python syntax/line lengths/trailing whitespace checked. ZIP CRC/exact nine-member
set and eight payload checksums verified; archive SHA256 sidecar verified.
No actual repository checks, native tests, Windows PowerShell, Ruff or mypy run.

Review then copy only absent additions. Run:

    .\scripts\qa\qa_policy_windows.ps1

Runner verifies expected branch/7a12a99 ancestry, prints actual HEAD/status/runtime,
checks dependency versions and runs focused integration then ALL mandatory QA:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Fail-fast; no commit/staging. New untracked-file whitespace checked separately;
git diff --check alone does not cover untracked files. Preserve unrelated logs.
Suggested commit ONLY after actual local QA:
feat(data-platform): detect forks rollback and denial removal in signed policy windows

Whole-platform acceptance/data-loading hold unchanged. Independently authenticated
governance evidence and persistent audited checkpoint/key lifecycle remain open.
