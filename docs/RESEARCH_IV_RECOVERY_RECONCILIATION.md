# Research IV store-scoped recovery reconciliation

Additive package; no existing module or fixture is replaced. Baseline c73def6 is
user-confirmed accepted and pushed; local HEAD/branch are not independently known.
Current consumer and CLI remain accepted, not "unconfirmed".

## API

`plan_research_iv_stage_recovery(staging, *, stage_build_id_pin,
expected_stage_fingerprint, artifact_root)` reads the exact reviewed first-stage
record, calls the existing two-pass inventory twice, then rereads the stage.
It never calls current native pricing, refreshes pins or performs recovery writes.
Use an existing read-only staging handle. No new CLI or mutation command is supplied.
The stage reader owns its existing read-transaction behavior; do not call inside
an already active caller transaction.

`reconciled_retain_only` requires stable complete observations, exactly one matching
bound artifact and no unresolved entries. This is a retain-only diagnostic, not a
new verification level, current-source acceptance or permission to execute recovery.
`review_required` retains digests of both complete inventories and stage observations
in a combined evidence digest. The result does not retain those complete bytes and
must not be described as exact retained-original replay.

Each other conforming file remains outside this one reviewed binding with ownership
unknown. Another dedicated stage store may own it. Never infer global orphan status.
Inventory metadata drift matters even if content hashes match. Root/inventory
exceptions and original stage failures propagate; there is no partial returned plan.

## Important source-reconciled limitation

The actual artifact reader rejects foreign/pending/nonregular root entries before
stage verification can finish. This package preserves that rule: such roots raise,
without cleanup. Use the independent inventory for their redacted diagnosis; do not
bypass stage verification to produce a linked recovery plan. Pure classifier tests
cover unresolved policy, not proof that the native reader accepts those roots.
Extra conforming regular files can be inventoried but are never adopted.

## Bounds and denials

Existing 256-entry, 4 MiB artifact and 16 MiB per inventory-pass limits remain.
Two inventories mean four passes, at most 64 MiB aggregate inventory body reads,
plus existing stage-reader reads. This is not a total-memory guarantee.
Plan encoding is bounded to 256 KiB. No global atomic snapshot or hostile concurrent
writer protection is claimed. Trusted single-owner roots remain required.
No cleanup/adoption/retry/recovery execution/publication/eligibility authority,
canonical identity, event time, availability or economic validity is introduced.
Failed original stage audit cannot be healed here. No user data is loaded.

## Delivery verification

Sandbox Python 3.12.8: 11 pure classifier tests passed. These tests execute the actual
new classifier; no native dependency replicas or successful native mocks are used.
All Python payloads parse; payload whitespace is checked separately from git.
Repository integration tests are supplied but NOT run in the sandbox. They use
existing actual stage/audit/model fixtures with the existing lower source substitute;
they are not full acquisition-native E2E.
Ruff and mypy are not installed in the sandbox. No repository QA, branch inspection,
commit, push, or full-native E2E was performed. Local mandatory QA remains required.

## Installation and local verification

Verify the archive using the standalone verifier and the separate archive SHA-256.
Extract to a disposable directory, inspect each addition, and copy only files whose
destination does not yet exist. Never overwrite an existing destination: reconcile
it against current local sources instead. No auto-installer or git staging is included.

Run the bundled PowerShell QA runner from the repository with ExpectedHead equal to
the explicitly reviewed FULL LOCAL `git rev-parse HEAD` output (40 lowercase hex).
It must not be c73def6, an artifact pin, ZIP digest or filename. Expected branch is
feat/medallion-feature-store. Runner stops on command failure and never stages files.
The verifier's --sha256 instead requires the separate 64-character ZIP SHA-256.
