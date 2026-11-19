# Native recorded-payload signature binding @1

## Source / baseline reconciliation

Latest user-reported HEAD remains 43d0b0dba1b63a214031375fd72728c142f69de3.
User confirmed prior IV-collapse/content-package QA. No QA/commit confirmation
was supplied for the most recently delivered pinned Ed25519 package. No local
repository access, branch proof, commit, staging or push by assistant.

Inspected uploaded identity_statement_reader.py, identity_statement_document.py
and test_identity_statement_reader_native.py. The signature files were NOT returned
by current uploaded-source discovery; this package depends explicitly on the last
delivered pinned-statement-ed25519@1 API. It does not re-deliver or overwrite it.
Install/review that package first and run this runner, which includes its tests.
If any new target already exists, stop and compare; never overwrite local fixes.
Python >=3.12, cryptography dependency and all existing schemas remain unchanged.

## Substantive new boundary

The prior verifier accepted standalone payload bytes. The new native reader
binds that cryptographic check to a specific exact recorded assertion through
fresh native content/history/audit/current-Bronze/JSONL checks. It does not accept
an archived or caller-constructed verified DTO as its source of authority.

    inspect_recorded_statement_signature(
        registry, bronze, assertion_id=..., request=UnderlyingAssertionRequest(...),
        record_id=..., original_plan=..., expected_plan_sha256=...,
        payload=..., signature=..., public_key=..., expected_public_key_sha256=...,
    )

Inputs are owned native connections as required by the existing content reader.
No outer transactions. No database opens, acquisition, initialization or writes.
The payload is explicitly caller-supplied, NOT claimed to be read from Bronze
by this service: its SHA256 must reproduce the exact request's recorded payload
pin, and independent local content/span checking must equal native content views.
Byte equality is established through SHA256 pins, under the same collision
resistance assumption as existing Bronze support; not an atomic byte reread.

Sequence:
1. Validate typed request and bounded immutable payload against exact recorded pin.
2. Invoke actual inspect_recorded_statement_content, including all existing native
   recording/current storage/JSONL derivation gates. Stop if incomplete.
3. Independently parse/match supplied original bytes using exact request fields,
   original-body byte span, fragment hash, record ID and payload hash.
4. Verify actual detached Ed25519 profile with explicit caller-supplied key pin.
5. Re-run the entire native content reader, even for an invalid signature/key pin.
6. Require complete before/after evidence, exact full DTO agreement and both native
   content views equal to the local match. Observed retry/history drift blocks.
7. Fingerprint both views and the signature/key/payload digest evidence.

Status recorded_payload_signature_bound_under_pinned_key is deliberately narrow.
A pin mismatch to the recorded payload raises a fixed ValueError. Native reader
failures propagate; they are not swallowed or converted to fabricated success.
Wrong key pins and invalid well-shaped signatures retain both native observations
in review_required. Malformed cryptographic inputs raise the prior verifier's
fixed input errors, with no success result or claimed after-observation.

## Trust boundaries

A cryptographic signature does NOT establish legitimate issuer/key ownership,
namespace authority, canonical identity, authorized revocation, temporal evidence,
acquisition authenticity, signature provenance, freshness or decision eligibility.
All corresponding flags stay false/None. Detached proof/key are caller inputs;
their receipt/provenance is NOT persisted or verified. No new trust root, approval,
revocation policy or namespace registration is seeded. Signed WITHDRAWN remains
an unverified withdrawal claim, not permission to revoke another statement.

Two complete native observations are sequential, not a cross-database atomic
snapshot; undetected changes that revert between observations are not ruled out.
The service cannot establish future continued validity. No old-good fallback.
No changes to legacy adapters, option_stream, Bronze formats or eligibility gates.
No live loading, migrations, backfills, publication, trading or loop cutover.

## Tests and delivery

Nine pure bounds/hash tests ran in sandbox and passed. They are NOT native E2E.
Eight native cases are supplied but NOT run by assistant: positive actual native
composition; signed DISPUTED/WITHDRAWN; wrong pin; different payload; actual retry
between observations; obsolete pin stopping before cryptography; invalid signature.
The tests import/reuse the actual uploaded native source_claim fixture, not a
reconstructed dependency/store. Mutation hooks wrap actual crypto and perform an
actual fixture retry; no mocked success path or fabricated cryptography.

Native tests, full repository checks, Ruff, mypy and Windows PowerShell were NOT
run here. New Python syntax, exact ZIP member set/CRC, payload and archive hashes
were checked. No dependency replicas, broad ignores, skips or weakened assertions.

Copy only absent additions after reviewing checksums. Run:

    .\scripts\qa\qa_recorded_statement_signature.ps1

The runner requires expected branch feat/medallion-feature-store, prints actual
HEAD/status/runtime, validates the prior signature version, runs previous/new
focused tests then all five mandatory QA commands, stopping at first failure.
Untracked files are not covered by git diff --check until tracked; new payload
whitespace was independently checked before delivery. Do not stage unrelated logs.

Suggested commit only after actual local passing QA:
feat(data-platform): bind pinned signatures to revalidated recorded statement payloads

Passing this package is not whole-platform acceptance. Issuer/namespace governance,
key lifecycle and signature acquisition evidence remain substantive next gates.
Data-loading/migration hold remains in force.
