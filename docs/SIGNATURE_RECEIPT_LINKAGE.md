# Native detached signature artifact receipt linkage @1

## Reconciled baseline

User reports commit 318999d on feat/medallion-feature-store and origin, with QA
and tests passed. This supersedes earlier user-reported 43d0b0d. No assistant
repository access, independent HEAD/branch verification, staging, commit or push.
Inspected CURRENT uploaded recorded_statement_signature.py, statement_signature.py,
their native tests, bronze_jsonl_support_reader.py and bronze_support_reader.py.
Current signature binding still explicitly leaves signature acquisition provenance
false. This additive package supplies proof-artifact storage/derivation linkage,
not acquisition authentication. Existing committed files are not included/replaced.
Apply only absent targets; if any target exists, stop and compare locally.
Python >=3.12 and all dependencies/thresholds/assertions remain unchanged.

## New format and exact target semantics

Platform-owned, NOT NSE/issuer standard:

- schema: statement-signature-artifact@1
- Bronze payload_format: statement_signature_json@1
- one canonical UTF8 JSON object, no newline, <=4096 original bytes
- exact keys: schema, assertion_id, record_id, payload_sha256,
  public_key_base64, signature_base64
- lowercase 64-hex assertion/payload pins, bounded record grammar matching the
  statement parser; canonical strict base64 for raw 32-byte key and 64-byte signature
- rejects duplicate keys, nonfinite values, unknown fields/schema, alternate JSON
  representation, trailing content, BOM, mutable bytes and malformed encoding

parse_signature_artifact verifies syntax only; even all-zero signature bytes parse.
It MUST NOT be interpreted as signature validity. assert/record/payload target fields
are administrative linkage claims in this artifact, NOT additional signer-endorsed
metadata: the existing Ed25519 signature still covers the original statement profile
only. No historical signature is auto-detected, relabeled or given a new scope.

## Native API

    inspect_signature_receipt(
        registry, bronze, proof_bronze,
        assertion_id=..., request=..., record_id=...,
        original_plan=..., expected_plan_sha256=..., payload=...,
        proof_support=BronzeSupportPin(...), proof_plan=...,
        expected_proof_plan_sha256=..., expected_public_key_sha256=...,
    )

No caller-supplied signature or public_key parameter: both are decoded from actual
pinned proof Bronze bytes. Caller still supplies a mandatory external expected key
SHA256. It is never learned/trusted from the artifact itself.

Proof support MUST cover the entire proof payload: start=0, end=actual byte count,
fragment_sha256=payload_hash, end<=4096. Statement payload remains the explicit
original bytes required by the existing binding API. The statement and proof use
separate exact original canonical JSONL import plans and reviewed plan pins.

Sequence: native proof JSONL/storage/audit observation -> bounded exact Bronze proof
row read and event validation in transaction -> strict artifact parse/target match ->
actual recorded statement/signature binding -> second native proof observation ->
second recorded statement/signature binding. Complete proof observations and complete
statement bindings must be unchanged in full. Both native services retain their
internal invalidation-first/history/audit/contract/derivation checks. No DTO import
as evidence. All SQL catalog/schema/table names use existing native quoting helper.
Native source payload materialization remains bounded by 1MiB and format parsing
by the stricter 4KiB proof bound. No bigger artifact prefix is accepted.

Positive: recorded_signature_proof_storage_linked and
proof_receipt_storage_linkage_verified=True. Fingerprint includes exact proof pin,
plan pin, artifact digest, both proof observations and both binding observations.
It does not JSON-serialize raw key/signature bytes into the fingerprint projection.
Result includes decoded proof bytes for typed in-process use; do not log asdict
blindly. No CLI or logging of payloads/plans/arbitrary exception bodies is supplied.

Unsupported/malformed source proof raises fixed-code rejection after rollback;
SQL/native exceptions propagate, not success. Incomplete initial proof, mismatched
target, invalid signature/key pin and observed drift return review_required. Early
failure does not claim later observations occurred. No fallback to old good evidence.

## Limits that remain deliberately unchanged

Storage receipt, retained original JSONL, plan binding and successful origin/scoped
audit are evidence of platform recording, NOT authenticated live acquisition.
Source/provider labels, asserted receipt metadata, self-hashes and operator actor
labels cannot identify an authoritative issuer. signature_acquisition_provenance_verified
and source_acquisition_authenticity_asserted remain FALSE. New positive flag names
only the narrower storage linkage; old nested DTOs are unchanged.

No key ownership, namespace authority, key lifecycle, authorized revocation,
identity truth/canonical ID, economic validity, publication availability or decision
eligibility is established. Signed withdrawal remains a claim. Multiple documents/
receipts are not globally resolved or enumerated by this exact-pin API. Sequential
observations are not atomic across databases, nor proof against change-and-revert
between reads or future changes. No anti-replay/signing-time assertion.

No DB opens, initialization, writes, acquisition, actual identity registration,
user loading/migration/backfills, publication, trading or decision-loop cutover.
Native owned file-backed connections/no outer transactions follow existing services.
No live attachment or Windows-unsafe filename is introduced.

## Tests and QA honesty

24 PURE artifact parser tests passed in Python 3.12 sandbox. These are not native
integration or end-to-end verification. Seven native tests supplied, NOT run by
assistant: real native stores/JSONL/audits/crypto, wrong target, wrong format, partial
span, wrong external key pin, real proof retry drift, real assertion retry drift.
The synthetic proof fixture uses ACTUAL BronzeEventStore, AuditLedger, import-plan
CLI and parser. Statement setup reuses current native fixtures. Retry hooks wrap
the real binding method and execute actual native retries; no simulated success.
No fabricated dependencies, skips, broad ignores or relaxed assertions.

All new Python parsed for syntax. All payloads checked for trailing whitespace;
ZIP CRC, exact six-payload-plus-manifest member set, payload and archive hashes
verified. Native/full-repository QA, PowerShell, Ruff and mypy NOT run here.

Run .\scripts\qa\qa_signature_receipts.ps1 after reviewing/copying absent files.
It checks expected branch, prints actual HEAD/status/runtime, validates binding
version, runs focused tests then all mandatory QA, stopping at first failure:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

It stages/commits nothing. Untracked files are not included by git diff --check;
new-file whitespace is independently checked in delivery. Preserve unrelated logs.
Suggested commit ONLY after actual local QA:
feat(data-platform): link detached signature artifacts to native Bronze receipt evidence

Passing this package is not platform completion; issuer/namespace governance and
independently authenticated acquisition/key-policy evidence remain open gates.
Data loading/migration hold stays in force.
