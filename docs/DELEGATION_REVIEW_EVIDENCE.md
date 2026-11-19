# Role-separated delegation review evidence @1

## Baseline and exact scope of delivery

Latest USER-REPORTED committed QA-passed baseline: e262db2 on
feat/medallion-feature-store and origin. No assistant local repository access,
branch/HEAD verification, staging, commit or push. Source exploration returned the
actual current checkpoint store/native-window/identity sources and tests, but three
targeted searches did NOT return checkpoint_native_revalidation.py or its new fixture.
Native integration therefore uses the explicit previously delivered, now user-reported
committed interface and a runtime version guard; it is NOT independently reconciled
against that newest source. No dependency replica or reconstructed consumer used.
No existing files replaced. Stop/compare if any target already exists locally.
Python >=3.12 and dependencies unchanged; cryptography is already declared.

User did not choose/register a real governance authority. Both distinct contracts
are supplied with synthetic fixtures, and NO production trust roots are configured.
This package does NOT complete independently authenticated governance authority.
It supplies a new concrete cryptographic control: role-separated two-key review,
anti-self-approval, explicit model/capability separation, conflict-set assessment
and exact checkpoint binding. No verified flag is renamed into authority.

## Models and schemas

INTERNAL_RESEARCH -> internal-research-delegation@1
EXTERNAL_ISSUER -> external-issuer-delegation-claim@1

Each wire document is exactly one canonical UTF8 JSON object, no trailing newline,
<=16384 original bytes. Common exact fields:

    schema, delegation_id, target, capability, statement_kind, evidence_refs

Internal additionally requires organization_ref (an UNVERIFIED exact label).
External instead requires claimed_issuer_ref and verification_method exactly
INDEPENDENT_EXTERNAL_REVIEW_REQUIRED. Unknown/fake verified methods reject.
Different field sets and caller-required expected_model prevent model downgrade.
External NEVER promotes to internal evidence or positive issuer authority.

Target exact fields:

    namespace, asset_kind, policy_id, governance_key_sha256,
    checkpoint_id, checkpoint_history_fingerprint

Namespace/policy grammar and INDEX/EQUITY follow existing contracts. All hash pins
lowercase 64 hex. No wildcards, alias/symbol inference, default namespace or automatic
key registration. Exact reviewed checkpoint/history is signed into the declaration.
Single permitted capability SIGN_RESEARCH_SCOPE_POLICY is a claimed administrative
scope only, NOT issuance/identity/withdrawal/rotation authority or an operative grant.
Any request for REVOKE_IDENTITY, ROTATE_KEY or another capability rejects.

statement_kind APPROVE, DISPUTE or WITHDRAW is literal review evidence. Dispute/
withdrawal requires review; even valid signatures never authorize revocation.

## Two-key role signatures

INTERNAL roles RESEARCH_OWNER and RISK_REVIEWER.
EXTERNAL roles AUTHORITY_REVIEWER and INDEPENDENT_REVIEWER.
Exactly one proof per required role, distinct raw 32-byte Ed25519 public keys,
64-byte signatures, and explicit caller-supplied expected SHA256 for EACH key.
The delegated governance key may not fill either role. No packet-supplied trust
root or actor_id lookup. Signatures cover both role and ORIGINAL packet bytes:

    b"nse-quant/delegation-review/ed25519/v1\x00"
    + len(role_ascii).to_bytes(2, "big") + role_ascii
    + len(original_bytes).to_bytes(8, "big") + original_bytes

Role relabeling, mixing signatures across packets, raw/nonprofile signatures,
wrong pins, duplicate roles/keys and delegate self-approval reject. Proof input:
ReviewerProof(role, public_key, signature, expected_public_key_sha256).
No private-key/signing service is implemented; framing helper is not a signer.

IMPORTANT: two distinct keys do NOT prove distinct humans, organizational roles,
legitimate approvals or independent organizations. A caller can control both keys
and supply matching pins. Reviewer identity/role authorization must be established
outside this API before any real organizational authorization could be claimed.
No internal_authorization_asserted or policy_authority_authenticated is set true.

## Evidence references and conflict semantics

1..8 exact claimed Bronze references with fields capture_event_id, envelope_hash,
payload_hash, byte_start, byte_end, fragment_sha256. Immutable original-byte intervals
0<=start<end<=1MiB, bool rejected. Duplicate reference objects reject. These references
are SIGNED CLAIMS ONLY: no Bronze connection is accepted by the offline assessor,
so supporting_bronze_refs_checked remains false. Hashes/ref syntax are neither actual
storage checks nor acquisition authenticity or external authority evidence.
Raw referenced artifacts stay upstream in Bronze; this package writes none.

assess_delegation_review_set accepts tuple of 1..8 DelegationInput(document,
expected_sha256, proofs). Every supplied packet/schema/signature validates before
assessment. Distinct document hashes or ANY negative/external/mismatched packet
requires review. No first/last/issuer priority; exact duplicates retained in the
observations/fingerprint. Malformed later packets cannot salvage an approved prefix.
Supplied-set completeness is false: no claim to discover all worldwide delegations,
revocations or conflicting packets. No currentness/validity clock is inferred.

## APIs and native consumer

    assess_delegation_review(
        raw, expected_document_sha256=..., expected_model=...,
        expected_target=DelegationTarget(...), proofs=(ReviewerProof(...), ...),
    )
    assess_delegation_review_set(
        declarations, expected_model=..., expected_target=DelegationTarget(...),
    )
    inspect_delegation_native_binding(
        <same native arguments as revalidate_checkpoint_native_policy>,
        declarations=..., expected_model=...,
    )

The native consumer derives target from the revalidated typed assertion request,
policy/key pins and exact checkpoint/history expectations. It DOES NOT accept a
caller-created native result or target as evidence. Only an internal matched
review set reaches the actual checkpoint-native consumer; external/negative sets
stop with no native check claimed. Actual source/checkpoint drift still blocks.
The prior consumer replays the original recording query separately from the current
assertion query; this package preserves that interface, not a substituted query.

Positive internal_review_evidence_bound_to_native_checkpoint sets only
internal_review_evidence_bound. Offline internal success sets only
approval_quorum_signatures_verified/internal_review_constraints_satisfied.
Neither means internal research use is authorized. External with even two good
signatures ALWAYS returns review_required for independent external verifier.
All issuer/namespace/identity/authority/revocation/eligibility flags false/None.
This is not a positive admission/identity contract or publication permission.

No cryptographic packet receipt/audit persistence, Bronze-reference inspection,
reviewer/organization authentication, temporal validity, latest declaration/approval
lifecycle or actual external verifier is provided. Those are explicit remaining
gates; importing this package must NOT promote flags. No new DB schema/initialization,
file probing, networking, credential reads, writes or new CLI. No actual authority,
approver keys, organization, policies or identities are registered.

## Verification and QA

42 sandbox tests passed using ACTUAL cryptography Ed25519 and generated disposable
keys, not native dependency replicas. These are focused document/crypto/set tests,
NOT native E2E or externally authenticated governance. Cover model separation,
exact target dimensions, self/duplicate approvals, role/profile binding, missing/
invalid/mixed proofs, capabilities, strict JSON/bounds/references, disputes/withdrawal,
conflicts, original-byte pins and fail-closed external verification.

Five native tests supplied, NOT run here: actual checkpoint binding; external
stopping before native; real checkpoint retry invalidating signed history pin;
disputed sets; scope mismatch. Tests re-export actual native fixture dependencies
and execute actual services locally. No mocked positive result; only fail-fast
boundary assertion for external branch. Native fixture/consumer not reconstructed.
No actual repository/full native QA, Ruff, mypy or Windows PowerShell executed.
Python syntax, line lengths/trailing whitespace, ZIP CRC/exact seven-member set,
six payload hashes and archive SHA256 verified. No skips, broad ignores or weakened
assertions/thresholds. User local QA remains mandatory.

Review/copy ABSENT additions. If any target exists, stop and compare. Then:

    .\scripts\qa\qa_delegation_reviews.ps1

Runner verifies expected branch/e262db2 ancestry, prints actual HEAD/status/runtime,
checks dependency version and runs focused plus all mandatory QA (fail-fast):

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

No staging/commit. Untracked file whitespace is checked separately in delivery.
Preserve unrelated logs. Suggested commit ONLY after actual local QA:
feat(data-platform): separate internal and external delegation review evidence

No live acquisition/loading/migration/backfill, production trust-root or approval
registration, publication/trading/cutover. Data-loading hold remains unchanged.
Package QA is not whole-platform acceptance or closure of authenticated authority.
