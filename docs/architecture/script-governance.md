# Script governance and audit rollout

The accompanying CSV is a seed inventory of known commands, not automatic complete
local discovery. Reconcile every .py/.ps1 entrypoint, scheduled task and imported
writer before declaring coverage complete. Retired wrappers may already be absent.

## Required command registration

command name/version; category; owner; source/target layer and datasets; permitted
write mode; domain write scopes; explicit date/entity/run scope; dry-run behavior;
input snapshot policy; output manifest schema; retry/rollback/recovery policy;
required audit fields; tests; caller and scheduled-job references.

## Category boundaries

Ingest can append source data. Normalize can append source-linked Silver revisions.
Build reads pinned inputs and stages Gold. Publish promotes a validated artifact/build.
Export serializes pinned data and must not repair it. Inspect reads domain data only.
Workflow sequences registered children and records a parent, without duplicated SQL.
A script doing several categories should expose explicit separate operations.

## Before each mutating/export execution

Validate scope/permissions and ownership, register plan/manifest references, acquire
appropriate lease/fencing, pin inputs, estimate changes, and reject unapproved modes.
Emit no raw credentials/argv. A dry-run may emit an explicitly requested plan artifact
but must not mutate domain tables or initialize production schemas. Audit the plan
through the audit owner, not by opening another writer to the live DB.

## At completion

Capture counts, quality, checksums, committed outputs, visibility state and error code.
Validate before publishing; reconcile crashes. SUCCEEDED is not inferred from a
subprocess starting or a file merely existing. Keep partial publication distinguishable.

## Retirement

Migrate callers/docs/tests and external schedulers first. A wrapper is removable;
a distinct calculation is not redundant merely because its name contains build/backfill.
Preserve original evidence, published history and audit records. Retention deletions
are privileged, scoped, planned, reviewed and audited; never a routine backfill action.

## Known urgent guards

Full option-row identity for backfills; preserve live ATM-IV source observations;
reject non-NIFTY bootstrap use; prevent empty/failed candle rebuild destruction;
keep retrospective regimes out of point-in-time operational use; prevent historical
policy export from overwriting operational publication implicitly.

A1 does not yet register or intercept existing commands. Runner integration and
exhaustive local inventory are A2 acceptance requirements.
