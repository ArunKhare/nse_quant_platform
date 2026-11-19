# Independent pinned Bronze JSONL derivation recomputation @1

## Source reconciliation

Latest USER-REPORTED baseline 0646140, HEAD and origin/feat/medallion-feature-store,
QA/tests passed. Local repository unavailable; branch/worktree/HEAD/committed bytes
are not independently verified. Actual current underlying_support_revalidation.py,
its cursor-based duplicate-handle correction and short IDs were inspected. Preserve
those fixes; no existing file is replaced. Python >=3.12/dependencies/Layer unchanged.

Actual bronze_import.parse_events and main, BronzeEvent/append_batch, native support
reader and DatasetContract were inspected. Native importer uses JSONL envelope v1,
base64 payloads, UTC-normalized envelope hashing and ordered batch fingerprints.
Its native parser uses ordinary json.loads; this new verifier rejects duplicate keys
and nonfinite tokens independently, under a NEW explicit profile/version. It does
NOT silently alter/reinterpret/rewrite the historical importer or its version.

## Gap closed, and remaining trust limits

A generic Bronze batch can be internally hash-consistent even if a caller supplied
events unrelated to input_artifact: append_batch trusts batch construction. Storage
checks therefore cannot establish artifact-to-event derivation. This package:
- independently decodes the ORIGINAL retained JSONL artifact bytes;
- recomputes exact payloads, receipt IDs, full canonical envelopes and hashes;
- compares EVERY member and ordering with the native fresh stored batch;
- binds the original reviewed import-plan bytes to actual artifact, batch, source/
  session sets, event count and origin/scoped job actor/code metadata;
- checks fixed importer command/config and actual registered native Bronze contract.

This proves current deterministic JSONL-envelope derivation under the new strict
profile, NOT historical execution attestation, external provider authenticity,
claimed issuer/identifier truth, contract identity or genuine live receipt. The
payload can itself contain an entirely fictional identity statement. No document,
CSV, PDF or market-payload semantic interpretation is performed. Nothing becomes
eligible for a decision because it can be parsed/recomputed.

## Pure API

    recompute_jsonl(raw_original_artifact_bytes) -> JsonlArtifact
    decode_import_plan(raw_exact_plan_bytes, expected_plan_sha256=<reviewed SHA256>)
    verify_plan_inputs(plan, artifact, batch_key=..., actor_id=..., code_revision=...)

New version bronze-jsonl-envelope-recompute@1. Immutable recomputed envelope objects
contain exact decoded payload bytes (excluded from repr), complete canonical envelope
JSON, receipt/envelope/payload hashes. This is a new production verifier, NOT a
replacement/stub of BronzeEvent or a harness replica. Native original parser is not
called by verification; actual native parser parity is exercised only in local tests.

No partial salvage. Required/optional envelope keys are exact. Duplicates/nonfinite
JSON, unsupported versions, bool-as-version, non-string fields, invalid base64,
unknown origin kinds, naive timestamps and duplicate receipt IDs require review.
Blank lines are ignored like the native parser, while original artifact bytes and
whitespace remain hash-significant. JSONL record ordering remains significant.
UTC-equivalent receipt/exchange timestamps recompute the same normalized envelope.
Missing exchange clocks stay None; empty exchange strings are NOT inferred as None.
Optional IDs must be nonempty bounded strings or None. Metadata whitespace and text
bounds are a documented stricter subset, not a silent native importer modification.

Bounds: artifact <=16 MiB, nonblank line <=1500000 UTF8 bytes, <=64 events, <=1 MiB
individual decoded payload and <=8 MiB total decoded payload. Plan <=64 KiB; scalar
metadata <=4096 UTF8 bytes. Native support profile limits remain in force. These are
materialization/evidence bounds, not a hard engine/CPU/peak-memory guarantee.

## Original import plan

The native importer hashes exact canonical plan bytes into job scope. Exact keys:
kind, version, input_hash, batch_key, events, sources, capture_sessions, target_db,
actor, code_revision, initialize. No unknown fields or bool/int coercion. Caller
must provide exact original canonical plan bytes and a separately reviewed SHA256;
the verifier does not reconstruct an old plan from today's DB path or defaults.

Fixed native command: ingest.bronze_events@1.
Fixed config hash: SHA256 of exact bytes
bronze-envelope-v1;10000-events;1MiB-payload;16MiB-artifact
(as in inspected native importer). Source reader audit expectation is DERIVED from
this command/config and sha256:<original plan hash>, not an arbitrary caller command.

Plan input hash, batch key, count and exact source/session sets must match decoded
artifact. Original and same-scope job actor/code must match the plan. initialize
remains a recorded plan intent, not proof of what initialization actually happened.
Original target_db is retained provenance TEXT. It is not dereferenced, used as a
live path, or required to equal a relocated archive's current physical path. No
credentials/network/paths are inferred or accessed from plan metadata.

Plan hashing/job consistency is still NOT authorization, a trusted issuer policy,
a signature or proof the original plan was produced by an uncompromised program.
This reader does not require/repair an original external ManifestStore directory.
Its supplied plan bytes are checked against the native stored scope; full manifest
workflow/retry linkage and actual code execution remain separate evidence gates.

## Native consumer

    inspect_jsonl_bronze_support(
        bronze, support=BronzeSupportPin(...),
        plan_bytes=<exact original plan>, expected_plan_sha256=<explicit reviewed pin>,
    ) -> JsonlSupportEvidence

Owned file-backed read-only connection, no enclosing transaction. Sequence:
1. Existing native pinned support check using fixed original importer expectations.
2. Native-table snapshot + independent strict artifact/event/plan/contract recomputation.
3. Repeat the complete derivation snapshot/recomputation.
4. Repeat existing native storage/audit check; require complete unchanged results
   and matching derivation observations. All original evidence remains nested.

The two middle snapshots require the inspected original Bronze DatasetContract:
bronze.event_variants@1, layer bronze, append_observations, exact keys/required columns,
owner capture. Actual native DatasetContract is used, not a weakened contract clone.
Its registered_at is only local contract registration metadata. Foundation contract
registration has no origin-job link, so this check does NOT invent a successful
contract-registration audit lifecycle or cryptographic authority for it.

All ordered stored member payload bytes/envelope JSON/pins must match recomputation,
not just an aggregate hash or unordered set. Fresh clean batch/root/same-origin artifact
restrictions are inherited unchanged; mixed/retry membership is NOT guessed. Middle
reads also enforce member count/aggregate-byte bounds. SQL and operational failures
propagate; malformed/unsupported data returns review, not a provider/identity rejection.
A later failed or changed derivation cannot be replaced by earlier success. Original
ingest audit obligations are not healed by a newer success. No writes, repair/adoption,
ingestion, schema creation, external acquisition or publication occur.

## Result semantics

Positive status verified_jsonl_recomputation permits these NEW, narrow claims:
- artifact_to_event_semantics_verified=True: original JSONL envelopes deterministically
  recompute exact native stored events under THIS explicit parser profile only;
- original_plan_binding_verified=True: reviewed plan matches observed inputs/jobs.

Nested BronzeSupportEvidence @1 flags are NOT mutated; its own semantics flag stays
False as originally defined. Existing underlying-support revalidation @1 is also
unchanged and does NOT automatically claim or consume this new proof. Integration
into identity assessments needs an explicit further contract, not boolean promotion.
identity_semantics_verified, source authenticity, issuer authentication, identity,
retry-link coverage, availability, historical validity and decision eligibility all
remain False. No canonical ID/binding is minted or unverified withdrawal authorized.

Matching observations are observed agreement across sequential Bronze transactions,
not an atomic lock/barrier or proof of no transient/ABA changes or future stability.
Fingerprints hash original plan pin, native storage evidence and derivation snapshots.
They are not signatures, full DB/DDL/file/WAL hashes or complete strategy replay.

## CLI

    uv run python scripts/inspect/inspect_jsonl_support.py `
        --bronze-db <existing-db> --support-file <support-pin.json> `
        --original-plan-file <exact-original-plan> --plan-sha256 <reviewed-hash>

Default: no-I/O plan, no execution imports, path probes, DB opens, directory creation,
network or credentials. Add --inspect to open existing Bronze read-only. Support file
is <=8192 bytes, strict JSON fields matching BronzeSupportPin. Plan bytes are bounded
and must be canonical/exact SHA-pinned. Payloads, plan JSON and arbitrary exception
text are omitted from summaries. Exit 0 means recomputation consistency, NOT identity
admission; exit 2 is review/argument error; exit 1 JSONL_RECOMPUTATION_INSPECTION_FAILED.
No execute/initialize/force/repair/network or schema migration mode.

## Validation and remaining gates

45 pure decoder/plan/planning tests ran in sandbox; native DB/provenance orchestration
tests remain local. Native tests use ACTUAL bronze_import PLAN construction/parser,
BronzeEventStore, AuditLedger, DatasetContract and source reader over synthetic files.
They deliberately construct hash-consistent wrong events, swapped order, duplicate
JSON keys, bad actor/contract, incomplete origin, observation drift and readonly/TZ
cases. This is not actual importer execution-manifest/provider/issuer end-to-end
verification, and no dependency replica/harness is shipped. See QA_REPORT.md.

Next substantive gates remain authoritative namespace/issuer/source identity semantics,
source-specific non-JSONL acquisition profiles, explicit identity/binding assessments
and separate temporal/eligible publication evidence. No data loading, migration, live
acquisition, repair, identity recording, decision-loop cutover or trading was performed
or authorized here. Package QA is not whole-platform acceptance; loading hold remains.
