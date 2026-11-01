# Audited native admission-input capture @1

## Purpose and API
capture_publication_admission(publications, target, publication_id=<exact pin>,
    request=AdmissionRequest(...), actor_id=..., code_revision=..., initialize=False)

Read-only file-backed publication registry; separate single-owner file-backed
receipt database; no enclosing transactions. Every attempt freshly invokes the
committed native admission service/publication verifier. There is no arbitrary
receipt import, offline-replay-to-authority, repair, publication or strategy path.

Both ACCEPTED_RESEARCH_ONLY and REJECTED policy results are captured. Operational
source/SQL failures fail the job WITHOUT fabricating an admission rejection. A
successful capture job means evidence was recorded, not that a decision was allowed.
All decision/availability/validity/current-source/replay-authenticity claims remain
as in the receipt, never upgraded by persistence. No market data loading/migration.

## Native post-publication contract, not a medallion relabel
These are decision-input business/audit records AFTER publication, not new Bronze,
Silver observations or Gold analytics. The existing DatasetContract Layer enum is
not widened or weakened. A native contract registry in decision_inputs records
exact versioned required-record/write semantics and a content fingerprint. It does
not impersonate Gold with invented event/publication columns or modify existing
medallion contracts. Foundation AuditLedger remains the job/lifecycle service.

Owned objects:
- decision_inputs.admission_schema_versions: version 1.
- decision_inputs.admission_contracts: immutable native contract bytes/fingerprint.
- decision_inputs.admission_definitions: full immutable policy-definition bytes and
  fingerprint keyed by policy version.
- decision_inputs.admission_receipts: immutable full receipt BLOB (including exact
  frozen request/source input), input/receipt identities, duplicated outcome and
  request metadata, reassessment links, recorded_at and first_job_id.
- decision_inputs.admission_attempts: each committed job/receipt/input hash link.

Only these decision_inputs objects and foundation audit namespace are allowed.
Output cannot be the source, a file alias/attached source or a legacy data store.
Owned SQL uses fully quoted catalog.schema.object names. No upstream table writes.

## Identity / exact bytes
Store publication-admission-capture@1, command capture.publication_admission@1.
Request revision hashes [store/policy/definition/contract versions, publication pin,
canonical UTC request]. Receipt identity stays the admission codec's exact SHA256
of bytes excluding receipt_id, not a timestamp or database key manufactured here.
Full frozen input is INSIDE immutable receipt bytes; no partial source projection.
The creator assesses, encodes and replays through the committed codecs, checks the
requested publication/request and false eligibility flags, then writes exact bytes.
A self-hashed caller-supplied receipt is never accepted by this API.

## Transactions / retries / history
Schema initialization requires explicit initialize. Contract and definition insert,
new immutable receipt and attempt link share ONE domain transaction. If any fails,
all of them roll back. Unsupported same-version contract/definition or stored
receipt content mismatches fail, never overwrite. No UPDATE/DELETE is issued.
Exact retries reverify source, reuse exact content and append a new audited job/
attempt. Changed observed source/audit evidence yields a new receipt for the same
request revision, retaining links to all bounded prior receipts without filtering
accepted/rejected status. Source rejections and research acceptance remain distinct.

Links describe request REASSESSMENT lineage, not permission to erase historical
facts or select old-good evidence. An exact older receipt reused later is not
revived by rewriting links. No current/head/latest selection API is supplied.
A future consumer must distinguish archived capture integrity from current-request
admissibility and must not restore authority merely by replaying an old receipt.

Audit lifecycle and domain commit are separate. Post-commit final audit failure
leaves genuine rows/attempts and a nonterminal job; it raises, not success. A new
successful retry records only its own lifecycle, never repairs the earlier job or
first_job_id. Stored rows/links alone DO NOT prove completed provenance or permission.
A verified capture/provenance consumer is the next required gate. The frozen receipt
still has replay_authenticity_asserted=False: application capture is not a signature
or authentication boundary against arbitrary privileged DB modifications.

## Clocks, caps and trust
request_knowledge_cutoff and request_economic_at are caller REQUEST clocks, not
source availability/economic intervals. recorded_at is local aware UTC capture
metadata, never substituted into source/request facts. No reading-time now() enters
receipt/request identities. TIMESTAMPTZ retries compare aware instants, not display
labels. Publication/staging/market data timestamps are preserved unchanged in input.

Upstream input <=8 MiB / receipt <=16 MiB. Local contract/definition <=32768 bytes;
prior reason JSON has bounded projection; old receipt reads use SQL CASE before
Python materialization. At most 1000 prior receipts linked for a new reassessment;
exact retries remain allowed at the bound. Attempts/audit grow append-only.
Independent registry and output snapshots are not one atomic information frontier.
Use trusted DB ownership and serialized writes; no crypto-auth/source-truth claim.
No full strategy/code/config/raw-source replay package is captured here.

## CLI
Default plan: no DB opens, writes, initialization, network or credential lookup.
--execute needs actor/code revision, existing publication registry and separate
output. New output needs --initialize; parent directory must exist. Input is opened
read-only. Archival profile rejects hidden time filters; decision profile requires
both explicit aware times and still captures REJECTED for research-only data.
Exit 0 after execution means COMMITTED capture, even with status=REJECTED. Exit 1
is ADMISSION_CAPTURE_FAILED without exception body; argparse errors exit 2.
No --allow-unknown, --import-receipt, --force-decision or publication option exists.

## Remaining acceptance
Verified native capture consumption/provenance, positive eligible decision inputs,
strategies/decisions and complete exact replay remain separate work. No data loading
or migration is authorized until platform acceptance gates pass.
