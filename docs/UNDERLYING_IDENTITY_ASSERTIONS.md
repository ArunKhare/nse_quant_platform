# Audited underlying identity assertions @1

## Reconciliation and purpose

Latest USER-REPORTED baseline: c4104f0 on feat/medallion-feature-store and origin,
QA/tests passed. Local repository/Git access unavailable. Inspected uploaded actual
derivative_description.py, native_derivative_description.py and documentation,
plus AuditLedger and existing dedicated native capture transaction patterns.
Descriptions still leave canonical IDs None; no independent underlying registry
or binding service was returned by discovery. This additive package records the
independent identity statements and supporting pins needed before later verification.
It does NOT claim those statements are true or that canonical identity is complete.
No existing description/frontier/reference code, user fixes, schemas or dependencies
are replaced. Python >=3.12 remains unchanged, no forced runtime downgrade.

## Architecture / owned objects

Raw source artifacts stay immutable upstream in Bronze. The new separate file-backed
identity_evidence namespace contains application reference-assertion/audit records,
not a replacement source artifact store or Bronze/Silver/Gold relabel:
- identity_evidence.schema_versions (native schema 1)
- identity_evidence.contracts (immutable native write semantics/fingerprint/origin job)
- identity_evidence.definitions (immutable assertion definition/fingerprint/origin job)
- identity_evidence.assertions (exact statement BLOB, scope, kind, history links,
  byte count, original recorded_at and first_job_id)
- identity_evidence.attempts (each committed recording job/statement link/recorded_at)
Foundation medallion_audit remains the native audit namespace. Layer enum and
DatasetContract are not widened or impersonated. Dedicated target rejects other
business tables and source/target path aliases, including attached sources.

## Pure API

    UnderlyingAssertionRequest(
        namespace, external_id, asset_kind, asserted_issuer, assertion,
        bronze_capture_event_id, bronze_envelope_hash, evidence_payload_hash,
        evidence_byte_start, evidence_byte_end, evidence_fragment_sha256,
        rationale_code,
    )
    make_underlying_assertion(request)
    encode_underlying_assertion(value)
    decode_underlying_assertion(raw, expected_assertion_id=<exact pin>)
    check_supporting_bytes(request, payload)

Assertion version underlying-identity-assertion@1. INDEX/EQUITY are initial supported
asset categories, not approval of an external identifier scheme. Namespace, external
ID and claimed issuer are explicit, bounded, case-sensitive strings. Syntax validation
is NOT namespace registration, issuer authentication, legal identifier verification
or proof that the asset exists. No alias expansion, case folding, trading-symbol
parsing or provider-name-derived identifiers. No literal production IDs are seeded.

ASSERTED, DISPUTED and WITHDRAWN are UNVERIFIED statement kinds. They are not platform
accept/reject outcomes, privileged commands or authenticated withdrawal actions.
An attacker or mistaken operator can make a statement. Durable recording must not
convert it into authority. actor_id/code_revision identify a recording attempt, not
an authenticated external issuer or access-control permission boundary.

subject_scope_id = hash([assertion version, namespace, exact external ID, asset kind]).
It groups comparable claims, not verified real-world identity. Claimed issuer,
assertion state, rationale and supporting evidence enter assertion_id, which hashes
the entire canonical result excluding assertion_id itself. Scope excludes issuer so
conflicting issuer claims are retained together. Different namespace/id spellings
remain separate; no cross-scheme equivalence or conflict completeness is asserted.
All canonical_underlying_id, identity_verified, issuer_authenticated, availability,
historical-validity and decision-eligibility outputs remain None/False.

## Supporting evidence and limits

Evidence is an exact existing Bronze capture_event_id + envelope hash + payload hash
and a nonempty half-open BYTE interval [start,end). Byte offsets are not character,
PDF-page or text-extraction locations. Fragment SHA256 covers exactly those original
payload bytes. Compressed/binary artifacts remain their received representation;
there is no decoding, parsing, external fetch or extraction inference.

Payload <=1 MiB; envelope <=64 KiB; assertion <=16 KiB; namespace <=64 characters,
external ID <=256, claimed issuer <=128, rationale uppercase code <=64. Identity
strings have an explicit restricted character grammar. A larger artifact requires
review/new explicit policy, not truncation or silent partial import.

The writer reads a single Bronze snapshot, requires exactly one variant under the
receipt ID, verifies exact payload/envelope hashes, canonical envelope version 1,
source/session/record links and recomputed capture-event identity, then validates
payload range and fragment hash. Bounded SQL projection precedes materialization.
A conflict or mismatched byte range fails execution rather than fabricating an
ASSERTED/DISPUTED rejection or approval.

IMPORTANT: this is BYTE INTEGRITY/LINK consistency only. It does not verify Bronze
acquisition audit/batch provenance, original receipt clocks, publisher identity,
signatures, publication/economic validity or whether the cited fragment supports
the claimed namespace/ID. A consistently forged Bronze row can pass this integrity
boundary. The stored result never asserts provenance, semantic support or authenticity.
Independent trusted source interpretation and full provenance consumption are next
gates. Hashes/self-consistent offline replay cannot replace them.

## Native writer

    record_underlying_assertion(
        bronze, target, request=UnderlyingAssertionRequest(...),
        actor_id=..., code_revision=..., initialize=False,
    )

Store underlying-assertion-store@1; command record.underlying_identity_assertion@1.
Owned read-only file-backed Bronze connection; separate dedicated single-owner
file-backed writer; no outer transactions. Every attempt freshly checks source
bytes. No arbitrary encoded assertion import or automatic upgrade to a binding.

Initialization is explicit. Native contract, definition, new assertion and attempt
are inserted in ONE domain transaction, with rollback of all if any domain insert
fails. Initialization and foundation audit lifecycle commits remain separate.
PLANNED -> RUNNING -> SUCCEEDED means an unverified assertion was recorded. No
PUBLISHED state. SQL/source failures raise; no manufactured business outcome.
After domain commit, final audit failure may leave real rows and RUNNING origin.
The service raises, and later successful retry neither repairs nor backdates origin.
The verified capture-provenance consumer is not supplied by this package: rows and
successful retries alone cannot discharge incomplete original audit obligations.

Exact retries preserve original immutable statement, clock, first job and history
links, appending only a new audited attempt after source rechecking. Changed support,
issuer, assertion kind or rationale produces a different statement. Before inserting
a new statement, all prior IDs for that exact subject scope are retained, without
kind/audit-success filters (<=1000 prior statements). Exact retries remain permitted
at the history bound. Same-version stored content mismatches fail; no UPDATE/DELETE,
repair, adoption or overwriting source artifacts. No expiry/availability time filling.

prior_assertion_ids_json describes previously recorded EVIDENCE, not authority to
erase or supersede other issuers' assertions. No current/head/active selector exists.
An exact ASSERTED retry after WITHDRAWN does not revive anything. Future consumers
must resolve ALL history and audit obligations before any quality/state filtering,
then apply independently verified issuer/namespace policy. They must not treat a
newer unverified withdrawal as an authenticated revocation or pick old-good claims.

recorded_at is local UTC recording metadata only. No other clock fields are invented.
Bronze observation and target commit are independent snapshots, not a cross-DB atomic
proof of ongoing source consistency or future availability. Trusted ownership and
serialized writes are prerequisites; AuditLedger is application evidence, not a
permission boundary against privileged SQL edits.

## CLI / no data execution in delivery

    uv run python scripts/inspect/record_underlying_assertion.py `
        --bronze-db <existing-bronze> --identity-db <dedicated-registry> `
        --request-file <typed-request-json>

Default plan does not import execution code, open/probe files/DBs, read requests,
create directories, initialize, use network or credentials. Execution requires BOTH
--execute and --allow-assertion-recording, nonempty --actor/--code-revision, existing
Bronze/request inputs and an existing target parent. New target needs --initialize.
The request JSON has bounded read and strict duplicate/nonfinite rejecting parsing;
extra fields cannot inject verified flags. Source opens read-only. CLI summaries
never print payloads or arbitrary exception text. Exit 0 after execution means
COMMITTED_UNVERIFIED_ASSERTION, including DISPUTED/WITHDRAWN; NOT verified identity.
Exit 1 is redacted UNDERLYING_ASSERTION_FAILED; argument errors exit 2.

No real identity statements, files, market data or supporting artifacts were loaded,
acquired or migrated during delivery. Code/tests use synthetic fixtures only.

## Remaining substantive gates

Next: verified read-only assertion/provenance/history consumption with full audit
obligations; explicit supported authoritative namespace/issuer/source verification;
independent canonical underlying identities and explicit derivative-row bindings;
conflict/invalidation semantics that distinguish unverified claims from authorized
revocations; temporal/publication evidence and positive decision admission. This
package supplies recording infrastructure, not those approvals. No derivative
provider label is automatically mapped, and no existing research-only receipt is
promoted. Package QA is not platform acceptance; loading/migration/cutover hold stays.
