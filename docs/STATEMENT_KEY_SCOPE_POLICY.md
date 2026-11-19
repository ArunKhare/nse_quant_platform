# Signed statement-key scope constraints @1

## Baseline / sources

User-reported QA-passed committed baseline cff7a52 on feat/medallion-feature-store
and origin. No assistant repository/HEAD inspection, commit/staging/push. Inspected
CURRENT uploaded signature_receipt_reader.py, signature_artifact.py, native receipt
fixtures, recorded_statement_signature.py and signature verifier. Current native
receipt flags deliberately do not establish namespace authority. No policy/key
lifecycle service was returned by discovery; absence is not proof of local absence.
Additions only: if a target exists, stop/compare, never overwrite a committed fix.
Python >=3.12/dependencies/native schemas/legacy adapters are unchanged.

## New actual policy capability

This is not another name for storage verification. It adds independently signed
policy-document cryptography, exact scope matching, full key-denial precedence,
ambiguity rejection and deny-by-default evaluation. A valid statement signature
can now fail conditional policy constraints despite perfect storage evidence.
It does NOT manufacture a legitimate governance authority or latest policy.

Schema statement-key-scope-policy@1, exact canonical UTF8 JSON object, no trailing
newline, <=65536 bytes. Exact fields:

    schema, policy_id, sequence, grants, denied_keys

Each grant has EXACT fields:

    grant_id, namespace, external_id, asset_kind, asserted_issuer,
    assertion, signer_key_sha256

Scope uses exact case-sensitive strings with the existing statement field grammar.
INDEX/EQUITY and ASSERTED/DISPUTED/WITHDRAWN are supported. No wildcard, alias,
prefix, symbol inference, delegation, implicit cross-namespace equivalence or ranges.
At most 128 grants and 128 distinct denied keys. Unique grant IDs. Sequence is an
integer 1..2147483647, bool rejected. All grants validate before any decision,
including after an otherwise matching grant or a known denied key.

Policy signature uses actual Ed25519, raw 32-byte public key/64-byte signature:

    b"nse-quant/statement-key-scope-policy/ed25519/v1\x00"
    + len(original_policy_bytes).to_bytes(8, "big")
    + original_policy_bytes

Explicit caller-reviewed policy SHA256 AND governance-public-key SHA256 required.
No trust-on-first-use, network key discovery, signing CLI, registration or persistence.
Wrong pins, invalid signatures, malformed/noncanonical documents raise fixed-code
ScopePolicyRejected. Duplicate JSON/nonfinite/unknown later fields never salvaged.

Rules after complete validation:
1. Signer in denied_keys -> denied_under_supplied_policy, even with matching grants.
2. Multiple exact matching grants -> review_required, no first/last/ID preference.
3. No exact grant -> denied_under_supplied_policy.
4. One exact grant -> permitted_under_supplied_policy.

A denial is a rule in THIS supplied snapshot, not authenticated real-world key
revocation, legal withdrawal or retroactive source invalidation. A WITHDRAWN grant
permits the statement kind under the policy only; authorized_revocation stays false.

## APIs and native composition

    assess_signed_scope_policy(
        raw, policy_signature=..., governance_public_key=...,
        expected_policy_sha256=..., expected_governance_key_sha256=...,
        query=ScopeQuery(...),
    )

    inspect_statement_scope_policy(
        <same connections and exact keyword inputs as inspect_signature_receipt>,
        policy_bytes=..., policy_signature=..., governance_public_key=...,
        expected_policy_sha256=..., expected_governance_key_sha256=...,
    )

Native entry derives the query from a revalidated typed assertion request and the
explicit expected signer pin, NOT a caller-supplied query or receipt DTO. It verifies
the signed policy then calls actual inspect_signature_receipt (even for a well-formed
denying policy). Receipt must be complete and its actual key hash must match the
query; native failures retain review_required. Invalid policy fails BEFORE native
execution; no receipt check is falsely claimed in that case. A positive fingerprint
binds policy/key digests, sequence, query, policy signature digest and native receipt
fingerprint. No mutation to the existing nested receipt or its flags.

Positive native status native_receipt_satisfies_supplied_policy only sets
supplied_policy_constraints_satisfied. Its governance_signature_verified inner
flag means cryptographic key-possession proof. authority/currentness/issuer/
namespace/identity/revocation/temporal/decision flags remain false and canonical
underlying ID None. This is NOT positive identity/admission or publication eligibility.

## Explicit governance gap, not a bootstrapped trust root

Anyone can create a policy AND supply its matching governance key/pin. Hashes and
signatures alone do not establish their legitimacy. No authenticated policy-authority
or independent namespace delegation evidence is supplied in this package.
No production policy, authority/key registration or literal real IDs are seeded.

Pinned bytes prevent substitution relative to caller expectation, not rollback to
an older still-signed policy selected by caller. sequence is a signed label, not
proof of the latest snapshot, chronological truth or anti-rollback state. No time
fields/validity dates, signing time, receipt availability or economic validity are
inferred. External independently authenticated authority/currentness evidence and
persistent lifecycle/revocation semantics remain gates before any positive trust.
No policy acquisition provenance or Bronze policy receipt is claimed. Policies are
caller-supplied original bytes. Do not confuse these conditional results with
independently evidenced issuer/namespace acceptance. Existing hold remains.

## Verification and QA

39 focused sandbox tests passed using real installed cryptography and disposable
Ed25519 keys, no replicated/mocked native dependencies. They cover scope dimensions,
key denial, ambiguity, strict profile/pins/schema, invalid later grants, bounds,
canonical JSON, malformed signatures and no authority escalation. They are NOT
native end-to-end tests. Six native composition tests supplied, NOT run here; use
actual source_claim/proof_store native fixtures and actual signed policies.

No actual repository checks, native integration/full suites, Ruff, mypy or Windows
PowerShell executed by assistant. All Python syntax parsed, payload whitespace
checked, ZIP exact member/CRC and every payload checksum/archive SHA256 verified.

Review/copy absent additions then run:

    .\scripts\qa\qa_statement_scope_policy.ps1

Runner verifies branch, actual HEAD and cff7a52 ancestry, prints working status and
runtime, then focused tests and all mandatory QA. Fail-fast, no stages/commits:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Untracked files are not checked by git diff --check; package whitespace checked
separately. No ignored/skipped tests, broadened thresholds or weakened assertions.
Suggested commit ONLY after actual passing QA:
feat(data-platform): evaluate signed exact-scope key policies with denial precedence

No live acquisition/loading/migration/backfill/real identities/publication/trading/
decision cutover. Package acceptance is not whole-platform acceptance.
