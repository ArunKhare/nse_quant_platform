# Targeted nonexecuting quote-bundle recovery inspection @1

## Scope
inspect_bundle_recovery(staging, bundle_id=<exact SHA256>, artifact_root=Path(...),
    policy=DEFAULT_RECOVERY_POLICY) -> BundleRecoveryPlan

One explicit bundle pin in a caller-owned read-only file-backed staging DB, no
outer transaction. No source DBs are opened or revalidated. Root is caller-supplied
and must match schema binding; no DB-provided arbitrary path is followed.
This is not the current-source stage verifier, a publisher or a recovery executor.

## Observations
- Dedicated staging namespace, schema/audit versions, root binding and contract.
- Exact target metadata, artifact hash/size/canonical content and manifest agreement.
- Bounded complete-or-explicitly-partial stage history without quality filtering;
  full captured graphs detect supersession/cycles/ambiguous or malformed links.
- Bounded jobs linked to the target or matching its known staging scope, latest
  states, first-job linkage, root-bound configuration, actor/code identity presence,
  missing job rows and unlinked/incomplete/failed/cancelled stage attempts.
- Successful jobs linked to another stage in the same scope are not mislabelled
  as unlinked. Scope matching can expose legitimate older failed attempts for
  conservative review; a finding is not proof that data is corrupt.
- A bounded directory PREFIX detects pending-file names. Pending payloads are
  NEVER opened/decoded, declared abandoned, adopted or considered ingestible.
  Pending names are hashed in reports. No association to the target is inferred.

Unknown target with no metadata/artifact is TARGET_NOT_OBSERVED, not automatic
permission to reconstruct it. Orphan artifacts can be content-valid without any
authority to adopt, publish or use them. Corrupt/missing files remain unchanged.

## Bounds and completeness
Defaults: 128 history rows, 128 matching jobs, 128 directory entries, 4 MiB target
artifact. Hard maxima: 1001 history rows, 1000 jobs, 1000 directory entries and codec
4 MiB byte cap. Policy rejects booleans/nonpositive/oversized numeric limits.
Each query/iteration consumes at most limit+1 rows/names to detect truncation;
reported counts refer to retained observations, NOT total unseen database counts.
Missing-job-link inspection is separately capped by the job limit.

Only the target artifact is read. Oversize artifacts are not read; hash stays
unknown and coverage incomplete. For a known stat size within the byte cap, read
at most size+1 (capped at policy+1), rejecting observed growth/shrinkage without
salvaging a prefix. Directory traversal is nonrecursive; unrelated artifacts are
not read or globally inventoried. Directory enumeration order is filesystem-defined;
retained bounded observations are sorted for reporting, not a full directory sort.

A bound hit, I/O failure, unavailable root or unsupported schema/binding produces
INCOMPLETE_REVIEW_REQUIRED, not a clean bill of health. With complete bounded
coverage, findings produce REVIEW_REQUIRED; otherwise NO_TARGET_FINDINGS means
only no findings in THIS target/scope/prefix. global_inventory_performed=False
and source_current_checked=False ALWAYS. NO_TARGET_FINDINGS is not source validity,
publication/temporal admission, safety, historical completeness or recovery approval.

## Nonexecuting plan
Every result has execution_permitted=False and false publication, historical
validity and decision-eligibility assertions. Review steps preserve evidence,
review target/audits and require a separately designed/approved recovery. They
contain no SQL repair statements, shell commands, automatic actions or executable
operation list. No audit lifecycle/job success is written or inferred.

plan_id hashes the canonical reported observations with plan_id="". It is not a
signature or checksum of all raw DB/audit evidence. Different raw states mapping
to the same review category can share a report identity. No current wall clock,
receipt/publication/effective time, file-age judgment or provider identity is
manufactured. Metadata/file/job reads use separate observation windows, not an
atomic snapshot or authorization barrier. Reports can become stale immediately.
Use trusted roots; symlink targets are not followed for target content, but these
checks do not defend against privileged concurrent filesystem replacement.

## CLI
Default emits a plan without DB connections, directory scanning or file creation.
--inspect opens metadata read-only and produces a review plan. No --execute,
--repair, --adopt or --initialize option exists. No actor/credentials/network needed.
Exit 0: default plan or NO_TARGET_FINDINGS. Exit 2: review/incomplete report, or
argparse error distinguished on stderr. Exit 1: bounded generic
RECOVERY_INSPECTION_FAILED without arbitrary exception text/partial JSON.
Missing/corrupt SQL objects may raise operational errors; they are not created.

## Remaining gates
Use read_staged_quote_bundle separately for current source checks. No staged
bundle repair execution, audited publication, temporal admission, decisions or
exact replay is provided here. Data loading/migration remains deferred.
