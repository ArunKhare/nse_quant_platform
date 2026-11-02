# Pinned-key statement signatures @1

## Reconciliation

Last user-reported HEAD: 43d0b0dba1b63a214031375fd72728c142f69de3.
User confirmed all previous tests and QA passed, including IV-collapse closure.
No assistant repository access, branch inspection, staging, commit or push.
Uploaded snapshots are not proof of local HEAD. Apply only absent additions;
if a target exists, stop and compare, never overwrite committed corrections.

Inspected identity_statement_document.py and identity_statement_reader.py.
The existing parser exposes VERSION underlying-statement-document@1,
StatementDocument and parse_statement_document(bytes). The native recorded
reader still returns matched_untrusted_statement_support with all trust flags
false. This package changes neither interface nor their implementations.

## New capability, not a trust wrapper

statement_signature.verify_pinned_statement_signature(payload, signature=...,
public_key=..., expected_public_key_sha256=...) uses actual cryptography Ed25519.
Payload is opaque original immutable bytes, 1..1048576 bytes. Public key is the
32-byte raw encoding, signature 64 bytes, and expected key SHA256 exactly 64
lowercase hexadecimal characters. No PEM, base64, algorithm negotiation, implicit
key discovery or key acceptance from the statement. Invalid input shapes raise
fixed-code ValueError; wrong pins and invalid signatures return review_required.
No arbitrary cryptographic exception text is surfaced.

The EXACT signing message is:

    b"nse-quant/underlying-statement-signature/ed25519/v1\x00"
    + len(payload).to_bytes(8, "big")
    + payload

Version: pinned-statement-ed25519@1. The NUL is one zero byte. LF/CRLF changes,
canonicalization, BOM insertion, trailing-newline changes and one-byte edits
change the signature input. There is no signing CLI or persistent key service.
signing_message is framing only; production private keys are never accepted.
Existing arbitrary raw-byte signatures are NOT auto-detected or relabeled.

signed_statement_document.inspect_signed_statement_document composes the actual
whole-document parser with cryptographic verification on those same original
bytes. It returns both independent results. Syntax errors anywhere reject the
whole document; a valid signature cannot salvage a valid prefix. Multiple
same-subject records remain present, including disputes/withdrawals; there is
no winner, revocation authority, alias inference or canonical ID allocation.
The parser version is explicitly checked. Byte limits remain unchanged.

## Security meaning

valid_signature_under_pinned_key means this exact profile verified with the
specified key. It does NOT establish who controls the key or who was authorized
to sign. A caller supplying an attacker's key AND pin can verify an attacker's
signature: this is expected, not issuer authentication. Pin provenance must be
independently established outside this API; no trust root is registered here.

All issuer, namespace-authority, identity, revocation and decision flags stay
false; canonical_underlying_id stays None. Inner evidence also keeps availability
and historical-validity false. The outer DTO exposes no positive temporal grant.
No asserted timestamp, signature creation time, key-validity window, revocation
status or replay freshness is inferred. Successful signatures can be replayed;
there is no anti-replay, authorization-policy or key-lifecycle claim.

The existing Bronze/recording reader is not bypassed, replaced or promoted. This
package does not link a signature to Bronze, acquisition audit or a recording ID.
It is an offline cryptographic building block, not native storage E2E or a positive
identity-admission service. Those source links plus independently governed issuer/
namespace policy and revocation/key lifecycle are future acceptance gates.
No database/network/filesystem access in either new API; no real key registration,
acquisition, user-data loading, migration, publication, trading or cutover.

## Tests and QA

19 sandbox tests passed using installed cryptography 46.0.0 and Python 3.12.8,
actual Ed25519 generated disposable keys, and the exact new module. No replicated
crypto/native dependency, no mocks, no native harness. Checks cover profile/domain,
length framing, byte substitution, key pins, wrong signers, immutable input shapes,
bounds, strict pins and non-escalation. These are focused sandbox tests ONLY.
Two actual-parser composition tests are supplied but NOT run by the assistant:
parser source was returned as an excerpt, not an importable sandbox dependency.
No reconstruction was used. Full repository/Windows QA, PowerShell, Ruff and mypy
were NOT run by assistant; Ruff/mypy are unavailable in sandbox. All Python payloads
were syntax parsed; ZIP CRC, member set and payload hashes verified independently.

Run scripts/qa/qa_statement_signatures.ps1 locally with uv on the expected branch.
It prints actual HEAD/status/runtime, runs focused tests then all five mandatory
QA commands, stopping on the first failure. It does not stage or commit. Existing
pyproject/Python >=3.12/dependencies are unchanged (cryptography is already declared).
Review SHA256SUMS.json before applying; checksum verification is not authentication.

Suggested commit ONLY after actual local QA:
feat(data-platform): verify exact statement bytes with explicitly pinned Ed25519 keys

Passing this package does not complete platform acceptance. Data loading and
migration hold remains in effect. Diagnostic documents with older baseline status
are historical and are not overwritten by this additive package.
