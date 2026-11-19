# Purpose-aware publication admission and frozen policy receipts @1

## Scope
assess_publication_use(publications, publication_id=<exact pin>,
    request=AdmissionRequest(...)) -> AdmissionReceipt
encode_admission_receipt(receipt) -> exact bytes
replay_admission_receipt(raw, expected_receipt_id=<exact pin>) -> reproduced receipt

The public creator always calls the native research-publication verifier and
freezes its exact DTO plus explicit request. No input/source registry writes,
strategy/execution, acquisition, publication, migration or audit repair occurs.
This is an admission-policy kernel, not durable/audited decision execution.

## Two explicit profiles
ARCHIVED_RESEARCH_ANALYSIS:
- verified RESEARCH_ONLY archived snapshot may yield ACCEPTED_RESEARCH_ONLY;
- knowledge_cutoff and economic_at must BOTH be absent. Supplying either rejects
  the REQUEST, not silently ignoring a hidden as-of filter;
- research_analysis_permitted is a policy outcome, not an ACL/access credential,
  authorization signature, current-source guarantee or decision permit.

POINT_IN_TIME_DECISION:
- both knowledge_cutoff and economic_at must be explicit aware datetimes;
- these are separate axes; no invented ordering or equality rule is imposed;
- protocol @1 research publications are ALWAYS rejected for this profile, even
  when the requested times are after the record/audit clocks;
- reasons preserve research-only purpose, unknown availability/economic validity,
  unknown canonical contract identity and unasserted decision eligibility;
- record/audit clocks, quote event/trade clocks and request clocks NEVER substitute
  for independently evidenced availability or economic intervals.

There is no allow-unknown, assume-valid, force-decision, latest-source or caller
permission override. Source flags claiming availability/decision validity under the
known research @1 contract are rejected as mismatches, not used to admit decisions.
A future positive decision lane needs independently verified eligible publication/
identity/temporal evidence and an explicit new version; this package cannot make
it by reclassifying old research/legacy data. It does not implement that future lane.

## Source contract / unknowns
Support research-quote-publication-consumer@1, RESEARCH_ONLY,
verified_research_snapshot and exact bundle content/identity checks through the
committed codec. Validate the native publication identity, original clocks as
canonical UTC labels and evidence/attempt pins. Those known clocks remain only
recorded facts. No comparison promotes them into availability or validity.
Source SQL/operational errors propagate rather than manufacturing a receipt of
success. Failed/unverified source evidence produces a deterministic rejected receipt.
Current Gold/staging/live sources are not looked up to answer a historical request.

## Frozen input and identity
Input document contains version, explicit publication pin, UTC-normalized request
and exact serialized ResearchPublicationEvidence (including full immutable bundle).
A receipt includes input SHA256, the frozen input JSON, policy version/immutable
rule-definition fingerprint, source IDs/fingerprint and deterministic outcome.
receipt_id = SHA256(exact canonical receipt bytes, excluding receipt_id itself).
No current wall clock/random ID enters the receipt. Equivalent timezone requests
produce equal IDs; changing request axes or observed source evidence changes ID.
Versions and unknown schemas cannot silently upgrade during decode/evaluation.

## What replay proves
Replay validates bounded exact bytes, checksum, strict duplicate/nonfinite rejecting
canonical JSON, input hash/schema/request, policy/definition and EXACT recomputed
result. Canonical byte equality prevents bool/integer coercion from overriding
flags. Both accepted research and rejected decision receipts reproduce offline.
No DB, live source, root or latest policy selection is consulted during replay.

This proves content integrity/policy consistency ONLY. Self-hashes are NOT source
authenticity, audit signatures, authorization or availability-as-of proof. Someone
can construct an input document that CLAIMS verified evidence; hashing/replaying
it cannot prove that a real native verification originally occurred. Accordingly
replay_authenticity_asserted=False always. Do not restore authority or bypass
registry access controls based on an offline receipt. Durable audited capture and
verified provenance consumption are further gates. Source DTO/audit fingerprints
also do not contain all raw/code/config/strategy evidence for full decision replay.

## Bounds / no side effects
Frozen input <=8 MiB, serialized receipt <=16 MiB; upstream codec/source reader
bounds still apply. Pure codecs preserve unknowns and never salvage prefixes.
No files are written by this package. Callers may explicitly retain returned bytes
but that is not an audited persistence/approval mechanism supplied here.
All decision/availability/economic-validity/current-source/replay-authenticity
assertions stay False, including ACCEPTED_RESEARCH_ONLY outputs.

## CLI
Default --publication-db --publication-id --use-case emits a no-I/O plan.
--assess opens the existing registry read-only and prints a bounded summary, not
full frozen source/features. Point-in-time profile also requires both explicit
--knowledge-cutoff and --economic-at timestamps. Archival profile rejects them.
Exit 0: plan or accepted archival research; exit 2: rejected assessment/argparse
error; exit 1: PUBLICATION_ADMISSION_FAILED. No --execute or initialization mode.

## Remaining gates / migration hold
Native audited admission/decision-input persistence, verified provenance consumers,
positive decision-eligible publication/admission, strategies, decisions and complete
exact replay are not finished by this kernel. Data loading/migration remains held.
