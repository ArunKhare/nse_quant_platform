# Signed temporal evidence bound to exact native research publications

## Baseline and reconciled scope

User reports 78272d0 committed/pushed on feat/medallion-feature-store and QA/tests passed.
The accepted key lifecycle, failure acceptance and earlier fixture fixes are unchanged.
Repository/terminal connector discovery returned none; local full HEAD/worktree not inspected.

Retrieved actual publication_admission.py, quote_bundle_publication.py, observed_key_lifecycle.py,
lifecycle_scope_policy.py, key_lifecycle_capture.py and governance/window foundations. Research
admission @1 explicitly rejects point-in-time use and does not treat audit/record clocks as
availability/economic-validity proof. Lifecycle @1 proves a supplied signed key chain, not authority.

Targeted retrieval did NOT expose existing generic temporal-selection implementation files.
This is NOT evidence that they are absent. This package neither replaces nor duplicates a generic
native temporal selector. It defines a DISTINCT bounded signed declaration artifact, causal
revision protocol and native exact-publication binding. It does not alter Silver/Gold selection.
No architecture/completion statements in old planning docs are promoted to native acceptance.

## Implemented protocol

signed_temporal_evidence.py validates a complete supplied series of exact signed records:
- Exact namespace/asset/publication-ID/bundle-ID/publication-evidence-fingerprint subject.
- Sequence from 1, full predecessor signed-record SHA-256, explicit reviewed tip.
- Each declaration pins the lifecycle prefix under which its signing key is observed active.
- ASSERT / DISPUTE / WITHDRAW with no same-series recovery/reactivation shortcut.
- Nullable declared availability and explicit nullable economic [from, until) interval.
- Exact hashes of supplied retained support bytes, not provider receipt times or symbols.
- Domain-separated actual Ed25519 signatures and canonical strict JSON.

Every supplied revision, support hash, interval and signature validates BEFORE any time test.
No filtering out future/negative/invalid revisions; no first/last-good selection or salvage.
Any DISPUTE or WITHDRAW is sticky across later assertions in this @1 series. It is a supplied
negative claim, not independently authorized revocation. A new series is NOT evidence that
older negative obligations disappeared; completeness across series remains unresolved.

The policy tests knowledge_cutoff and economic_at as separate explicit axes. Available-at <=
knowledge-cutoff is inclusive. Economic interval is [from, until); start inclusive/end exclusive.
Null endpoints remain UNKNOWN, never inferred from receipt/audit/publication clocks or infinity.
Canonical signed clocks use aware UTC ISO strings. Request timezones normalize to UTC, but
noncanonical signed clock strings reject rather than rewrite original bytes. No order is imposed
between cutoff and economic_at. Matching numbers/intervals never prove source-time truth.

## Native integration

native_publication_temporal.py uses actual native services:
1. Reverify the complete supplied observed governance-key chain (existing lifecycle @1).
2. Read the actual reviewed publication; require its exact ID and FULL evidence fingerprint.
3. Derive each declaration's verifier key by revalidating its pinned actual lifecycle prefix.
4. Require the final declaration signer to remain active in the complete supplied chain.
   A rotation can require a new signed revision, not silent refresh of old claims. Prior
   signatures still verify under their own pinned prefixes. A terminal lifecycle revocation
   blocks this lane. Global key currentness/authority remain unverified.
5. Verify/evaluate all temporal declarations; create and completely replay retained claim bytes.
6. Repeat the actual publication read and require complete canonical observation equality.
7. Run ACTUAL existing point-in-time admission, verify its full frozen source matches the last
   publication observation, and replay its retained receipt exactly. Existing @1 must REJECT.

No caller-native DTO, signer-key override, allow-unknown, trust boolean or eligible override.
Publication and admission SQL/operational failures propagate, not fabricated policy denials.
Observed source drift returns review-required; no old-good cache or fingerprint auto-refresh.
The underlying publication reader is ARCHIVAL. publication_snapshot_rechecked does NOT mean
live source_current_checked. All live-source, independent availability, economic validity,
identity, issuer/root/namespace authority, authorized revocation, historical validity,
cross-database atomicity and decision eligibility denials remain false/None.

The native service issues no writes, publication, registration, acquisition or user-data action.
Tests seed the actual disposable producer path via accepted NativeFailureLab and use real
lifecycle signatures, native publication reader and admission evaluator. No source/model result
is substituted. Between-invocation file mutations test invalidation, NOT concurrent race coverage.

## Retained replay boundary

encode_temporal_receipt retains COMPLETE original signed declaration envelopes, support blobs,
verification public keys, exact pins, subject, independent request axes and full original result.
replay_temporal_receipt redoes signature/chain/time checks and requires complete canonical equality.
A rehashed outer result cannot promote independent verification flags. No IV-only/scalar/tolerant
comparison or caller result trust. Changing keys/support/subjects/clocks remains visible.

This codec is original CLAIM evaluation replay, not proof of root/issuer authority, publication
acquisition, source currentness or complete original strategy/decision replay. The pure receipt
does not retain the complete native lifecycle/publication observations; the native result carries
those observations/fingerprints separately. Do not relabel the pure receipt as native E2E replay.
No new archive, database schema, CLI or automatic persistence/recovery profile is added.
Existing immutable archives, first-write captures and their obligations are untouched.

## Bounds

- 1..16 records, <=8192 document bytes, <=18432 signed-record bytes.
- <=262144 aggregate signed-record bytes.
- 1..16 support blobs, each <=65536 bytes, aggregate <=262144 bytes.
- <=2097152 serialized retained receipt bytes.
- Native publication observation <=16777216 serialized bytes.
- Actual existing key lifecycle bounds preserved (<=64 events); at most 16 prefix verifications.
All are explicit payload/operation bounds, not total-process-memory limits. No existing bound,
solver, tolerance, dependency, native assertion or numerical model setting is changed.

## Evidence still required for a real positive lane

These signatures are only key possession under supplied roots. Support byte hashes prove
integrity, not independently sourced timestamp truth. Real positive eligibility still requires:
- Independently authenticated issuer/namespace authority and authorization to attest time.
- Authoritative identity binding for the actual instrument/resource, not a publication self-hash.
- Independently verifiable provenance, clock semantics and availability/economic-validity evidence.
- Sufficient scope, causal history/completeness, revocation/currentness and conflict resolution.
- A DISTINCT reviewed eligible publication/admission contract and complete native strategy inputs.
No such independent real evidence was supplied. No real trust registration or root shortcut exists.
Signed synthetic claims may mechanically match; production admission remains blocked.

## Tests and verification

Pure real-crypto tests cover boundaries, distinct axes, timezone normalization, null semantics,
negative revision precedence, causal conflicts, wrong pins/subjects, later invalid signatures,
strict JSON, retained support integrity, actual capacity gates and complete receipt replay.
Native integration tests cover actual producer-path refusal with matching claims, unknown/future/
expired/withdrawn claims, exact source pins, rotation/reassertion, terminal key revocation,
between-invocation source drift, retained replay and operational SQL failure propagation.

Assistant executed 26 pure actual cryptographic/codec tests: PASSED. No native dependency replica
or substituted successful computation. Native integration tests are supplied for repository QA,
NOT independently executed here. Repository pytest/Ruff/mypy/Git/Windows uv not run. AST, Python
line length, whitespace, exact ZIP members, CRC and per-payload/whole-archive hashes verified.
User-confirmed prior QA remains accepted, not re-executed. No whole-platform acceptance claimed.

## Acceptance ledger

| Remaining gate | This package | Still blocked / not implemented |
|---|---|---|
| Governance | Uses actual accepted lifecycle prefixes/retirement | Independent trust root/issuer authority and real key ownership |
| Identity | Pins exact publication subject without canonical inference | Authoritative underlying and derivative binding |
| Temporal | Signed revision, support-byte, interval and request-axis mechanics | Independent provenance/time truth and generic selector reconciliation |
| Eligible publication | Actual research-contract refusal remains mandatory | Distinct sufficient positive admission contract |
| Lifecycle/recovery | Sticky supplied negative declaration semantics | Authorized cross-series recovery and operational research lifecycle |
| Native decisions/replay | Full signed claim replay plus actual admission receipt replay | Complete strategy inputs and actual original-decision replay |
| Operational | Bounded disposable native tests supplied | Native operational/real-evidence acceptance, concurrent races |

Apply only additive files after whole-ZIP verification; refuse existing destination conflicts.
Use qa_publication_temporal.ps1 with an explicitly reviewed FULL 40-character LOCAL Git HEAD.
It prints actual uv interpreter/dependencies and executes all mandatory QA. No staging, commit,
push, log deletion, live loading, production publication, trading or cutover is performed.
