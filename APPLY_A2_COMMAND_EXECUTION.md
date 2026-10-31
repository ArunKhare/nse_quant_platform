# Next package: A2a command execution

Extract this additive package into your feature branch after reviewing name collisions.
It depends on the QA-passed A1 foundation; do not replace A1 audit.py or contracts.py.

Read docs/architecture/a2-command-execution.md before integration. No broker/production
DB command is supplied. Test in disposable databases first.

Included are command definitions/bindings, explicit execution scope, immutable plan
and result manifests, an A1-compatible audited runner, unit tests and integration tests.
Default dry-run returns a plan without creating files, audit rows, or invoking a callback.

Not included: automatic registration/discovery of every script; live workflow migration;
writer permissions; source-preserving backfill guards; publication transactions;
crash reconciliation; an end-to-end production feature store. Do not delete scripts.

Run:

    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform tests/data_platform
    uv run mypy
    git diff --check

In this environment only the 26 A2 unit cases were executed, against a recording
ledger double. Real A1 integration and project-wide QA must run locally. Hard-link
publication must be tested on your deployment volume; unsupported filesystems fail
closed instead of falling back to destructive replacement.
