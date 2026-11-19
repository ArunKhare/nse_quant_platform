# Exact recorded untrusted statement content @1

## Reconciliation / commit boundary

User reports all tests and QA passed for the previous independent JSONL derivation
package and asks to commit/build next. No new Git hash was supplied. Last explicit
USER-REPORTED HEAD remains 0646140 on feat/medallion-feature-store with origin shown.
No local C:\Projects\nse_quant_platform access: no commit/push/checkout/staging was
executed and Git/worktree state is not independently verified. See README_PATCH.md
for scoped previous-package commit instructions. Do not infer an unreported hash.

Inspected actual uploaded bronze_jsonl_recompute.py/support_reader.py and tests,
underlying_support_revalidation.py/native tests and underlying assertion request
schema. Current interfaces match the preceding @1 definitions. Existing cursor
shared-handle, Windows-safe alias/filename and short pytest-ID fixes are preserved.
No existing file, native decoder/parser, schema, Layer or dependency is replaced.
Python >=3.12 remains unchanged; no runtime downgrade or dependency reduction.

## New platform-owned format, NOT an external authority

This package specifies a NEW application document profile:
statement_schema = underlying-statement-document@1
Bronze payload_format = underlying_identity_statement_jsonl@1

It is NOT an NSE, government, exchange, depository, legal identifier or issuer
standard. Its namespace/identifier/issuer strings are unverified statements. There
are no seeded production IDs, allowed trusted issuers or canonical mappings. A fake
document can match a fake assertion exactly. Matching is not acceptance of its truth.
Do not relabel arbitrary existing artifacts as this format or regenerate old evidence.
Unsupported document formats require a separately versioned parser/verification path.

Each record is canonical UTF8 JSON with EXACT keys:
statement_schema, record_id, namespace, external_id, asset_kind, asserted_issuer,
assertion. Supported kinds are INDEX/EQUITY and ASSERTED/DISPUTED/WITHDRAWN. Values
are bounded exact strings with restricted identifier grammar, no case folding,
symbol parsing, alias inference or normalization into canonical underlying IDs.
No validity/publication/availability timestamp fields are invented or accepted.

Records use LF or CRLF separators. One optional final newline is allowed; blank
records, BOM, bare trailing CR and noncanonical record whitespace are rejected.
Byte offsets refer to the ORIGINAL payload bytes, excluding each record's line
ending. CRLF consumes two bytes between records, not one. They are not character,
PDF page or text-extraction offsets. The payload hash includes all separators.
A caller's existing fragment range is never adjusted/rebased/trimmed to force success.

## Pure APIs

    parse_statement_document(payload_bytes) -> StatementDocument
    match_statement_content(payload_bytes, expected=StatementExpectation(...))

StatementExpectation independently pins record_id, all five claim fields (namespace,
external_id, asset_kind, asserted_issuer, assertion), exact payload/fragment SHA256
and byte_start/end. Validate the entire document before looking up the exact record.
Reject duplicate/nonfinite JSON, unknown schemas/fields, wrong types and duplicate
record IDs, including duplicates on unrelated subjects. Unsupported later records
cannot be filtered out to salvage a matching prefix.

All records with the exact requested (namespace, external_id, asset_kind) are counted
BEFORE assertion-kind or issuer preference. More than one same-subject record requires
independent resolution, even if they repeat the same claim or one says WITHDRAWN.
No first/last/current/issuer-priority or old-ASSERTED fallback. This is conservative
subject ambiguity, NOT authorization of an unverified dispute/revocation. Other
subjects are schema-validated but their truth/conflict completeness is not asserted.

A unique explicit record must match all five fields AND exact record-body span/hash.
Any mismatch returns review; unsupported whole-document structure raises a bounded
StatementDocumentRejected code. A result with statement_content_matched=True and
record_span_verified=True is literal content/locator consistency only. Identity,
issuer authentication, historical-validity, availability and eligibility remain false.

Bounds: original payload <=1 MiB, canonical record <=8192 bytes, <=256 records;
namespace <=64, external ID <=256, asserted issuer <=128, record ID <=64 characters.
No truncated/partial salvage. Bounds do not assert hard wall-clock or peak memory.

## Native recorded content API

    inspect_recorded_statement_content(
        registry, bronze,
        assertion_id=<exact pin>, request=UnderlyingAssertionRequest(...),
        record_id=<explicit document record>,
        original_plan=<exact canonical original JSONL import-plan bytes>,
        expected_plan_sha256=<reviewed original plan hash>,
    ) -> RecordedStatementContent

Separate owned existing file-backed read-only inputs, no enclosing transactions.
The native current-recording gate enforces exact request/pin, full recording history,
last-distinct evidence position and audit obligations BEFORE document selection.
Old pins after later dispute/withdrawal/unsupported or failed evidence cannot reach
content matching. Known original failures are not repaired by a successful retry.

The verifier then uses the actual independent JSONL derivation service, never the
historical permissive parser as proof. It requires the stored payload_format marker,
rechecks native receipt/envelope/byte integrity, and matches the requested content.
It brackets content inspection with repeated full JSONL derivation and recorded
support revalidation. Full native DTO/fingerprint comparisons include the complete
observed registry history and scoped source audits. All eight returned base storage
fingerprints must agree across the composed views, not just each pair independently.
Exact retries, new source conflicts and new registry evidence therefore require
review when observed between these calls. Later negative evidence is retained.

Before/after native results and document match remain nested evidence. A nested
positive match does not override the top-level review outcome. SQL/source errors
propagate, never fabricated business rejection. No source/registry writes, audit
repair, schema changes, acquisition, publication, canonical binding or cutover.

Positive status matched_untrusted_statement_support means literal recorded-content,
source-byte and JSONL-envelope consistency. All identity_verified, issuer_authenticated,
canonical_underlying_id, authorized_revocation_asserted, availability/economic-validity,
decision eligibility and atomic-cross-database assertions remain False/None.
A sole matching WITHDRAWN record can match literally but is NOT an authorized revocation.
Actual issuer authorization, scheme legitimacy, legal identity existence and binding
approval require independent policy/evidence. No allow-unknown or force option exists.

## Clocks, replay and atomicity

No now(), inferred receipt/publication/economic interval or expiry instant is added.
Underlying native UTC-instant comparison is preserved. Sequential native transactions
and matching fingerprints detect OBSERVED changes only, not transient/ABA changes,
simultaneous availability or future stability. No multi-resource lock, atomic frontier,
strategy-input authorization or decision permit is acquired. Fingerprints are content/
observation commitments, not signatures, issuer credentials or complete strategy replay.
Pure parser outputs can be fabricated and have no recording provenance by themselves.

## CLI

    uv run python scripts/inspect/inspect_identity_statement.py `
        --identity-db <existing-registry> --bronze-db <existing-bronze> `
        --assertion-id <exact-pin> --record-id <exact-record-id> `
        --request-file <native-assertion-request.json> `
        --original-plan-file <exact-original-plan> --plan-sha256 <reviewed-hash>

Default is no-I/O planning: no file probes, DB opens, execution imports, directories,
network or credentials. Add --inspect to open existing DBs read-only. Request <=16 KiB,
plan uses native <=64 KiB bound. Inputs are strict JSON with no extra trust flags.
Output omits raw payload/request/plan bytes; exceptions are redacted. Exit 0 is a
literal untrusted match, NOT identity/trading admission; exit 2 review/argument error;
exit 1 IDENTITY_STATEMENT_CONTENT_FAILED. No initialization/loading/repair path.

## Verification and remaining gates

36 pure document/content/span/planning tests passed in sandbox. Native tests invoke
actual local parser/plan/store/ledger/assertion writer/current recording/JSONL readers
on synthetic documents. Mutation spies call actual services rather than fabricated
verified-result implementations. Native tests remain unrun here and are NOT genuine
provider/issuer authenticity or full strategy/decision E2E. See QA_REPORT.md.

Next substantive requirements: authenticated issuer/scheme provenance and policy,
independent canonical underlying identities, explicit conflict/revocation-authorized
binding assessments and separate eligible temporal/publication evidence. This schema
is a deliberate untrusted content contract, NOT a substitute trust root. No actual
identity/market loading, migration, acquisition, repair, trading, publication or
cutover was performed/authorized. Package QA is not whole-platform acceptance.
