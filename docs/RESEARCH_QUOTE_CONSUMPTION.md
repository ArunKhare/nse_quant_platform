# Verified research-publication snapshot consumption @1

## API
read_research_publication(publications, publication_id=<exact lowercase SHA256>)

One owned read-only file-backed registry connection, no enclosing transaction.
No Gold/Bronze/Silver/staging connections or artifact root argument. The root in
registry metadata remains a provenance LABEL used for the original audit config;
it is never resolved, opened or required to exist. An archived snapshot therefore
does not silently depend on current live source state, artifact location or storage
platform. No writes, initialization, repairs, latest selection or publication.

## Versioned record and exact content checks
Capture one registry read transaction: dedicated namespace, schema/audit version 1,
registered Gold contract, exact publication record, all bounded linked attempts
and full bounded event sequences. Supported protocol is independent of the writer's
current constants: research-quote-publication@1 / research-only-publication-policy@1 /
RESEARCH_ONLY. The existing v1 bundle codec must be available; unknown versions block.
Recompute publication identity from the exact version/purpose/bundle tuple, verify
manifest BLOB SHA256/length/canonical codec content/member count/membership hash,
original stage approval, root-bound job config and all explicit false validity/
eligibility flags. Registry data cannot opt into trading by changing purpose.
Original staged manifest bytes and their creation-stage false flags remain intact;
verified research-publication relationship belongs to the publication envelope.

## Full lifecycle, not latest-state-only authority
Every linked attempt must have nonempty job/actor/code identifiers, correct
command/scope/config, exact approved=verified evidence pin and valid event indices.
Successful attempt requires EXACTLY:
PLANNED -> RUNNING -> STAGED -> VALIDATED -> PUBLISHED -> SUCCEEDED.
Missing phases cannot be hidden by a latest SUCCEEDED event. Contiguous indices,
known states, aware recorded clocks and bounded reason-code rules are checked.
Failed/cancelled attempts may terminate a valid prefix; CANCELLED after PUBLISHED
is invalid under foundation v1. All linked attempts must be terminal. A pending
retry blocks the current registry verification despite an earlier success.

The ORIGINAL first_job_id must be linked, match the record's first stage-evidence
fingerprint and have its own complete successful lifecycle. A later successful
attempt cannot backdate or substitute authority for a failed original publication.
Terminal failed retry evidence is preserved but is not success. Unlinked jobs grant
no authority. This is application evidence integrity, not cryptographic identity,
ACL enforcement or detection of every possible privileged database alteration.
No missing event/approval is invented or fixed by the reader.

## Clocks and historical meaning
publication_recorded_at exposes the writer's known UTC application record-creation
clock. origin_audit_success_recorded_at exposes the original success event's
recorded clock. They are kept separate; neither is asserted to be an exact commit,
external availability, provider-publication, receipt or economic-validity instant.
No monotonic wall-clock order or economic interval is manufactured. Timestamp
comparisons/fingerprints normalize aware instants to UTC, not session display labels.
availability_time_known=False, historical_validity_asserted=False and
 decision_eligibility_asserted=False ALWAYS.

status=verified_research_snapshot and research_publication_verified=True describe
an intact, auditable RESEARCH_ONLY archived record. They do NOT mean current-source
eligibility, present market validity, retrospective as-of availability or permission
to trade. source_current_checked=False ALWAYS. There is no --as-of argument and no
live-source fallback/recomputation hidden inside the reader. Current registry audit
validation can block after later incomplete retries without deleting historical
content. This API is not a full immutable audit-as-of replay engine or revocation API.

## Bounds and errors
Maximum manifest BLOB: 4 MiB, selected via SQL CASE before Python materialization.
At most 1000 attempts and 6000 events, each event sequence at most 6 rows for this
protocol. Contract/root/actor/code/state/reason fields have bounded projections.
Truncation/unknown policy/corruption/audit gaps block with no bundle. Invalid pins
or in-memory registry raise ValueError; missing/broken SQL objects and ordinary
operational failures propagate. No automatic schema upgrade or recovery is done.
Owned SQL is quoted catalog.schema.object; catalog named gold/escaped aliases work.

## CLI
Default --publication-db/--publication-id emits a nonexecuting no-I/O plan.
--inspect opens the existing registry read-only. Summary excludes manifest feature
payloads and row-stored filesystem paths; no exception body is printed.
Exit 0: default plan or verified research snapshot. Exit 2: blocked result or
argparse input error; exit 1: PUBLICATION_INSPECTION_FAILED. No --execute, --repair,
--initialize, --as-of or decision-admission mode exists.

## Remaining gates
Live freshness checking, policy-authorized temporal/knowledge admission, native
decisions and complete exact replay are separate modules. Snapshot bytes do not
contain all upstream raw/code/config evidence. No loading or migration is authorized
until the remaining platform acceptance gates pass.
