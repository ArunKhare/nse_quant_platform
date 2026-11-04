# Migrated-price research bundle prerequisite

## Delivery scope

This additive package implements legacy-price-research-bundle@1, a complete,
source-linked native bundle assembly and offline recomputation contract. It is
NOT publication, an audited persisted bundle store, admission, or platform acceptance.
It introduces no replacement modules and performs no migrations or registrations.

Inspection found a genuine prerequisite: quote_bundle_publication publishes only
read_staged_quote_bundle evidence and encode_quote_bundle content;
quote_publication_reader decodes only quote-feature-bundle@1; publication_admission
hardcodes that reader, quote schema and publication identity. research_iv_bundle_store
is an IV-scenario archive, not a generic publication registry. Reusing these by
relabeling migrated values would assert false provider-price/scale semantics.
The prerequisite here establishes a different typed, replayable content contract
before a separately versioned extension of native publication can be implemented.
No existing @1 reader, admission policy or production registration is modified.
This package does not complete the requested publication producer/reader path.

## Contract and APIs

LegacyGoldBundleRequest requires separately reviewed build and recording pins.
assemble_legacy_gold_bundle calls actual revalidate_legacy_price_gold twice and
actual _recording twice, retaining every full Silver input and Gold output from
one entire persisted build. Native failures propagate, without partial success.
A complete build can contain 1..16000 rows. No selection or multi-build grouping.

replay_legacy_gold_bundle checks the outer bundle hash, exact canonical manifest,
current Gold definition/runtime, all retained source content, full Gold
recomputation and original build identity. It does NOT authenticate the retained
recording-fingerprint declaration or original audit. Rehashing a changed but
well-formed recording fingerprint is intentionally possible offline; the native
assembler/revalidator rejects it against the real original recording.

revalidate_legacy_gold_bundle first replays content, then invokes actual current
native assembly and compares complete bytes. It never checks current legacy SQL.
All operations are read-only; actual Gold reader enforces read-only connection.
Caller owns and closes connections; no output database or artifact root is written.

The schema retains full Gold definition, runtime, source revision and fingerprint,
all Silver lineage including Bronze capture/partition/source event references, and
all Gold features and legacy-derived fields. Runtime equality retains the accepted
Gold @1 restriction; labels are not authenticated build/interpreter attestation.

Research purpose is explicit; canonical identity is null; independent availability,
economic validity, publication, decision eligibility and atomic cross-database
snapshot claims are false. Repeated matching reads are not atomic temporal proof.
There is no positive admission API. Existing quote admission cannot accept this
bundle. POINT_IN_TIME_DECISION remains unavailable, not bypassed.

## Resource bounds

Original Gold source/output row and aggregate limits remain independent. Decoder
checks array counts and hex string lengths before decoding; complete offline bytes
are capped at 140000000 bytes, accommodating hex encoding of up to 32 MiB of full
inputs plus 32 MiB of outputs and bounded metadata. This intentionally duplicates
complete evidence, not a compact production transfer format. JSON parsing and
assembly are bounded but materialize multiple copies; peak memory exceeds the raw
artifact size. There is no streaming or unbounded scan claim.

## Audit/failure semantics

This is read-only assembly, not a new first-write persistence profile. It inherits
actual Gold/Silver/Bronze readers' original obligations; it cannot heal/adopt jobs,
orphan rows, domain failures or final-audit failures. A future persisted native
publication extension must add its own original domain/audit obligations; none is
claimed here. No production publication or real data use is authorized.

## Tests and verification attribution

New repository tests reuse the actual accepted legacy -> partition Bronze -> Silver
-> Gold producer fixtures, then exercise the new native assembler and offline
reader. They cover full 1001-row/two-partition coverage, missing/reordered/duplicate
content, metadata/claim tampering, reviewed pins, original upstream/final audits,
second-pass operational failure, resource preflight, and separation of offline
replay, current native upstream and current legacy SQL.
These tests are supplied, NOT assistant-executed in the repository. No synthetic
successful reader DTO is substituted and called E2E. There is no claim that new
publication persistence/domain-failure tests ran: no such producer exists here.
Assistant checks are restricted to syntax, whitespace and archive integrity.

User-confirmed QA through 6e82773 is accepted and closed. It does not cover these
new additions. No Windows, uv-selected interpreter, Git worktree, commit or push
was independently inspected. Runtime log logs/live_status.json is untouched.

## Applying additions

Review/copy absent additions only; stop and compare if a destination already exists.
No accepted dependency belongs in this ZIP. No QA runner, scripts/qa, payload hash
manifest or standalone ZIP verifier is supplied. Repository-focused checks, full
QA and release review remain necessary for these additions; previously accepted
QA must not be rerun merely to resolve historical delivery documentation.

Real data loading/migration, live acquisition, production publication, authority
registration, trading and cutover remain HELD.
