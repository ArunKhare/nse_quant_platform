# Signed governance-key lifecycle mechanics under a supplied root

## Baseline and source reconciliation

User-reported committed/pushed baseline: f5d9bd5 on feat/medallion-feature-store;
QA and tests passed. Prior accepted 3c26011 fixture repair and 37733d7 joint attribution
are preserved. No new reported failure. Local full HEAD/branch/worktree not inspected.

Inspected actual statement_scope_policy.py, policy_window.py, signed_policy_window.py,
native_policy_window.py, native_statement_scope.py, delegation_review.py, audit.py and
existing scope-policy cryptography tests. Existing @1 signed policy windows use one key,
with sequence labels but no predecessor hashes; they explicitly provide no key rotation.
Delegation review verifies supplied role-separated signatures but not external authority.
Those contracts are unchanged. This package adds a distinct versioned causal-key contract;
it does not relabel observed policies/delegation as authenticated governance.

## Implementation and integration

observed_key_lifecycle.py verifies complete supplied original signed-event records.
Each event binds schema, exact series/namespace/asset-kind/policy-id, root-key pin,
contiguous sequence, predecessor FULL signed-record SHA-256, active subject and action.
The canonical signed envelope includes the original document and both signature fields.
Every envelope and root is explicitly pinned; no sorting, prefix salvage or auto-latest.

ROTATE requires the current active Ed25519 key's CURRENT-domain signature and the new
key's SUCCESSOR-domain possession signature over the same document. It retires the old
key permanently within the supplied chain. An introduced/retired key cannot be activated
again. REVOKE requires the active key's signature, no successor, and is terminal. This is
bounded self-revocation under a supplied root; it is NOT authorized external revocation.
Compromised active-key recovery, emergency rotation, organizational quorum, root replacement
and real issuer approval are NOT implemented. Two keys do not establish two people/roles.

lifecycle_scope_policy.py re-verifies original chain bytes, derives the active governance
public key (caller cannot override it), and invokes the ACTUAL existing scope-policy verifier.
Namespace, asset and policy-id must match. Existing denied-key precedence and ambiguous
scope-grant refusal are preserved. Lifecycle and policy sequence numbers are separate axes.
Policy pin/signature shape and full requested context remain bound even on terminal refusal.
No timestamps are created or inferred as source availability/economic validity.

key_lifecycle_capture.py retains COMPLETE chain input bytes, root and pins in a dedicated
file-backed evidence database under the ACTUAL AuditLedger. The complete original native
result DTO bytes are also retained; replay requires full canonical equality, not a hash-field match. This is evidence capture, not
key/root/identity registration. It verifies/encodes original bytes, never imports caller DTOs.
The retained-policy API reads a reviewed capture, verifies its complete original recording,
reconstructs signed inputs and invokes the lifecycle/scope integration again.

## Persistence semantics

The capture profile is explicitly first-write-only per content capture ID. Existing captures
are refused BEFORE planning another job, so a forbidden exact retry does not poison a good
record. Earlier scoped failed/incomplete/unlinked work is a blocker; it is not adopted.
Schema initialization, domain+attempt commit and final audit success are separate steps.
A failed final audit can leave complete retained bytes and a RUNNING job. Later calls cannot
repair/adopt it. Domain-link failure rolls back its record/attempt but retains the audit failure.
There is no retry/adoption/supersession/cleanup/recovery API. Other independent snapshots are
not authoritative superseders; caller must review exact pins. No global latest is selected.

Readers check original job identity, all scoped jobs and attempt coverage, contiguous exact
PLANNED/RUNNING/SUCCEEDED lifecycles, contract/schema bytes, bounded original input hash,
full cryptographic reconstruction and evidence fingerprint under one database read snapshot.
Use owned read-only connections without outer transactions; writes require single-owner output.
Recording verification is not continued validity/currentness or an atomic cross-resource barrier.
Application immutability is not protection against privileged SQL, whole-file rollback or deletion.

## Resource contracts

- 1..64 immutable supplied records; no empty/bootstrap registration profile.
- Document <=4096 bytes; signed record <=12288 bytes; aggregate chain <=524288 bytes.
- Retained encoded input <=1048576 bytes (stricter encoding overhead may reject large chains).
- At most 256 scoped jobs/links in a recording review; no success-only filtering.
- Execution labels <=256 characters; retained input/text projections bounded before transfer.
- All hexadecimal pins are exact lowercase SHA-256. No tolerance or hash refresh.
These are payload/coverage limits, not total process-memory ceilings. No limits were enlarged.

## Adversarial tests

Real disposable Ed25519 tests exercise valid rotations, possession-domain separation, terminal
revocation, late invalid signatures/actions, causal gaps/forks/order, wrong root/scope, strict
JSON, byte/count/aggregate bounds, retired-key reactivation and supplied-prefix limitations.
Integration tests invoke the actual scope verifier for current-vs-retired key signing, denial,
ambiguity, exact series/scope, terminal refusal and full refused-input fingerprint changes.
Native DuckDB/AuditLedger tests exercise retained replay/read-only reopening, non-poisoning
first-write refusal, final-audit failure, unlinked scoped work, corruption, wrong pins, quoted
catalogs and domain rollback with original failed work retained. No successful native dependency
is mocked. Only a final audit write is fault-injected; real source computation still runs.

## Acceptance ledger and unresolved evidence

| Gate | Added evidence mechanics | Still unresolved |
|---|---|---|
| Governance/key lifecycle | Cryptographic causal rotation, possession, terminal self-revocation; audited retention | Independent root/issuer/organizational authentication, real key ownership and authorized recovery |
| Identity/revocation | Scope/policy pins and mechanical key retirement | Canonical underlying/derivative identity and independently authorized revocation |
| Temporal evidence | No receipt-clock promotion | Independent availability and economic-validity evidence |
| Eligible publication | No change to research publication/admission @1 | Distinct sufficient positive eligible contract |
| Research lifecycle | Separate evidence capture, immutable first-write failures | Operational suspension/retirement/recovery contracts |
| Native decisions | Existing accepted research refusal suite unchanged | Complete strategy inputs and actual original decision replay |
| Operational acceptance | Disposable mechanics/failure tests supplied | Full native/real-environment acceptance and independent real evidence |

ALL root authority, namespace authority, issuer/identity, globally latest/currentness,
authorized revocation, availability/historical validity and decision-eligibility claims stay
false/None. A caller-selected self-signed root can satisfy mechanics and still has NO authority.
A valid supplied prefix can omit a later revocation: completeness/currentness remains false.
A mechanically positive result is only matched_supplied_constraints, never production admission.
No real acquisition/loading/migration/backfill/authority registration/publication/trading/cutover
is performed or authorized. No completion percentage or whole-platform acceptance is asserted.

## Applying and verification

All payload paths are additive. Verify whole ZIP with the separate digest before extraction;
do not overwrite an existing path without reconciling it. No pyproject or existing source edits.
Use qa_key_lifecycle.ps1 with a separately reviewed FULL 40-character LOCAL git rev-parse HEAD;
short commit IDs and ZIP hashes are not ExpectedHead values. Runner prints actual uv executable
and Python version, runs focused tests, both full pytest suites, Ruff, mypy, tracked and untracked
payload whitespace checks. It never stages, commits, pushes, deletes logs or loads user data.

Assistant executed 22 real-cryptography/kernel tests against the new actual module under Python
3.12.8 / cryptography 46.0.0: PASSED. No foundation dependency was replicated or substituted.
Scope-policy integration and native AuditLedger/storage tests are supplied for repository QA,
NOT sandbox-run. Full repository pytest/Ruff/mypy/Git/Windows uv checks NOT RUN. AST, line length,
whitespace, archive CRC, unique members and all payload/whole-archive checksums were verified.
User-confirmed baseline QA remains accepted evidence, not independently re-executed assistant QA.
