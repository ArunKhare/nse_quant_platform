# Verified staged quote-bundle consumption @1

## API
read_staged_quote_bundle(bronze, frame_silver, reference_silver, assessments, gold,
    staging, bundle_id=<exact SHA256>, artifact_root=Path(...))

All connections are caller-owned/read-only, no enclosing transactions. Staging
must be a file-backed dedicated metadata catalog and separate from all inputs,
including attached paths/file aliases. Artifact root must be separate from DB
paths. Caller supplies the expected root; the reader NEVER trusts an arbitrary
DB-stored path to choose where to read. Root resolution/binding must match.
No initialization, schemas, file creation, audit transitions or repairs.

## Verification sequence
1. Capture one bounded staging metadata read transaction: dedicated namespace,
   schema/root/audit versions, complete group graph, selected record, contract,
   every bounded linked attempt and latest relevant job state/identity metadata.
2. Resolve the FULL graph before seal-state, supported-version or success filtering.
   Failed/unsupported successors still invalidate old stages. No latest/old-good
   fallback or automatic change of the explicitly requested bundle pin.
3. Check native contract/version/state, exact artifact name/hash/counts, unknown
   event/publication times, first-job link and all active-stage attempt audits.
4. Read at most bundle limit+1 bytes through bounded artifact I/O, verify canonical
   manifest/checksum/content and agreement with stored byte/member/membership
   counts. Recompute scope from exact manifest pins and staging/bundle versions.
5. Freshly invoke the native two-pass Gold assembly for the stored pins. Controlled
   source rejection blocks; unexpected operational/SQL/source exceptions propagate.
   Require exact canonical byte agreement, not merely matching member IDs/prices.
6. Recapture staging metadata and reread the artifact. Observed metadata/artifact
   drift blocks without retry, repair or partial output.

The final checks detect observed changes; they are NOT one atomic filesystem/
DB/source transaction or an as-of information frontier. Changes after final reads
remain possible. Snapshot coverage concerns selected/group/linked audit metadata,
not every unrelated ledger column, file or historical job.

## Audit policy
All linked attempts of the active stage must have the exact command, scope and
root-bound config hash, nonempty actor/code revision identities, terminal states,
and at least one SUCCEEDED result. Terminal FAILED/CANCELLED attempts are retained,
not counted as success. A pending linked retry blocks despite earlier success.
A successful fresh retry does not erase an earlier incomplete linked job. No
missing success or original job state is synthesized. first_job_id must be linked.
Unlinked jobs grant no authority; the API is not a global orphan-job health scan.

## Fail-closed review outcomes
Missing/invalid artifact, missing root, wrong binding, orphan file, bad metadata,
unsupported versions/temporal claims, graph errors, audit gaps or current source
drift return blocked with no bundle. Uninitialized/broken SQL objects and ordinary
I/O/permission failures may raise operational errors; they are not initialized or
misreported as success. Invalid pins/configuration/database role aliases raise.

Orphan files are not adopted. Missing registered files are not recreated. Corrupt
bytes and incomplete audit jobs are not altered. Root loss is not silently healed.
Only the exact requested artifact is read; there is no directory-wide unbounded
scan, truncation, deletion, resealing or repair execution path.

## Output / identity
StagedQuoteBundleEvidence.status=verified_current means metadata, audit evidence,
artifact bytes and observed current source reassembly agree. It is NOT publication
or decision eligibility. The returned immutable bundle retains all its original
false publication/validity/eligibility flags and unknown times.
The evidence fingerprint covers version, bundle ID, expected root, selected
metadata/audit snapshots and exact artifact hash. No local read wall clock or
recording-time substitution is introduced. Recording/created timestamps are not
used to infer economic validity or information-availability cutoffs.
Stage attempt job IDs are distinct from Gold member attempt job IDs in the bundle.

Bounds: 1001 history nodes, shared resolver's 1000 links/node, 100000 bytes/link
JSON, 1000 linked stage attempts, codec's 64 members/4 MiB bundle. Native Gold
revalidation limits/costs also apply; no high-throughput or atomicity promise.

## Trust / completion boundary
Checksums are not signatures or protection against arbitrary concurrent filesystem
replacement/DB writes by privileged actors. Use trusted roots and owned connections.
This is not historical as-recorded replay, a publisher or an authorization gateway.
Next: bounded nonexecuting recovery planning and separately authorized publication/
temporal admission. Data loading and legacy migration stay deferred until platform
acceptance; no provider timing, IV/Greeks or canonical identity is invented.
