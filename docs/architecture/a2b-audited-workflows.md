# A2b: audited sequential workflow orchestration

Status: additive implementation. Requires the QA-passed A1 and A2a packages.
No existing workflow, command executor, database or setting is modified automatically.

## Implemented

WorkflowDefinition(name, version, owner, immutable ordered steps).
WorkflowStep(step_id, registered command/version, explicit ExecutionScope, required flag).
WorkflowRunner preflights every child through CommandRunner dry-run before any manifest,
audit job or actual child invocation. Invalid child scope/registration fails the whole
workflow before side effects, even if that child is optional: optional applies to
execution failure, not an invalid plan.

A real run saves its content-addressed plan, creates a parent audit job, and executes
children sequentially through the existing command runner with parent_job_id.
A child outcome must identify its audit job and result receipt to count as success.

Required failure: stop, mark subsequent steps NOT_RUN, save a failure summary when
possible, raise WorkflowFailed with report and chain the original exception. A1 marks
parent FAILED. Optional failure: continue, preserve failure reason, finish with
SUCCEEDED_WITH_WARNINGS in the workflow receipt. A1 parent state is SUCCEEDED because
it has no warning state; consumers must read the workflow receipt for degradation.

Success receipts identify successful child jobs/results. On a child exception, A2a
does not expose its job ID on the exception. The failed step outcome therefore has
no direct child_job_id; inspect audit jobs under the parent plus command identity.
Unique step IDs do not yet propagate to A1 child job metadata. Multiple same-command
steps require ordering/plan inspection. Adding explicit step correlation is future work.

## Files

src/nse_quant/data_platform/workflows.py
tests/data_platform/test_workflows.py
tests/data_platform/test_workflow_integration.py

This module uses public A1/A2a interfaces; it does not overwrite them. No dependencies.

## Example wiring pattern (not an executable live workflow)

1. Register trusted, already-reviewed service functions in CommandRegistry.
2. Give each step the exact scoped and pinned inputs it needs.
3. Construct WorkflowDefinition with required=True by default.
4. For an approved nonblocking status digest, set required=False explicitly.
5. Construct WorkflowRunner(CommandRunner(...), ledger, manifests) under the single
   owner process using the same initialized audit ledger and manifest store.
6. Call run(...), which defaults to dry_run=True; review its plan before execution.
7. Call with dry_run=False only under the approved database ownership policy.

The caller must verify registered functions are read-only or source-preserving as
declared. This is trusted service orchestration, not a sandbox or SQL authorizer.

## Why existing daily/EOD files are not overwritten

The available Project Files did not contain the user's current migrated workflow
versions. Replacing them would risk reintroducing retired wrappers and losing local
changes. Integrate against local HEAD in a separate adapter patch after A2b QA.

Daily workflow behavior to preserve explicitly:
- exports, readiness, backtest and report remain required where currently required;
- digest remains nonblocking only if deliberately declared optional;
- subprocess adapters must raise on nonzero exit, not return it as successful output;
- data scopes and actual pinned outputs must remain faithful to the existing operation.

The generic runner requires pinned inputs for build/export. It must not fabricate
snapshot references for mutable legacy tables. Add a proper reader/snapshot adapter.
A workflow whose later steps consume earlier outputs needs versioned artifact/input
binding. This package does not resolve dynamic DAG dependencies or mutate scopes.
Do not register a pretend static snapshot to bypass that missing integration.

## Preflight vs actual child plans

Preflight plan excludes the not-yet-created workflow job ID. Actual child plans include
that ID; they therefore legitimately have different hashes. Parent plan records the
preflight plan and child receipts/audit contain actual plans. Registry bindings and
scopes must remain unchanged for the duration; no concurrent reconfiguration supported.

## Failure and recovery boundaries

No rollback of completed child effects, no distributed transaction, no retries,
timeouts, leases, fencing, parallel scheduling or resumable checkpoints are implemented.
Do not blindly retry a failed workflow; inspect already-committed children first.

KeyboardInterrupt/SystemExit propagate rather than being treated as optional failures.
A1 handles parent cancellation/failure according to its existing contract. A final
workflow receipt is not guaranteed for cancellation, process kill or power loss.
Crash reconciliation/outbox remains future work.

Plan write failure prevents execution. Parent-job creation failure may leave an
unreferenced plan. Receipt failure after completed children marks the parent failed;
completed domain effects remain. If saving a required-failure receipt itself fails,
WorkflowFailed still chains the original child error and has receipt_id=None. An
exception note reports the receipt error type without recording arbitrary secret text.

The workflow definition itself is plan-addressed rather than persisted in a global
workflow registry. Definition/config immutability across deployments is established
by manifest + pinned code; fleet-wide command registry enforcement remains future work.

## Acceptance and tests

11 isolated unit tests passed with recording ledger/manifest/child doubles.
Three integration cases using the actual A1/A2a classes are included for local QA;
not executed in the packaging environment. No broker or live DB was accessed.

Run locally:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform tests/data_platform
    uv run mypy
    git diff --check

Use disposable DBs and test the manifest filesystem behavior on the deployment volume.
No scripts should be deleted during this additive patch.

## Follow-on

Add explicit step/job correlation and dynamic output-to-input binding before adapting
the actual dependent daily/EOD pipelines. Integrate one nonmutating workflow first.
Keep urgent original-data protections separate and prioritize them before registering
legacy mutation commands as production services.
