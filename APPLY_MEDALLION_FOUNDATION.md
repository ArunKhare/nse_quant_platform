# Medallion foundation bundle

This is a reviewable additive patch, not an applied repository change or a completed
production feature store. Architecture documents distinguish target requirements
from the implemented A1 primitives.

Start with docs/architecture/medallion-conceptual.md and medallion-implementation.md.
Review namespace/file collisions, then extract source, scripts, tests and docs at
repository root. No existing settings, live writers, data, schemas or trading gates
are modified by extraction. initialize() creates new audit objects only when called.

Run the local validation commands in the implementation document. Use a separate
disposable audit database or an in-memory connection initially, not the live DB.

The initial code is useful but does not prevent old scripts from overwriting data.
That protection requires writer migration and enforcement in the next patches.
The audit API is append-only by convention, not protection against direct SQL or
privileged modification, and does not roll back arbitrary domain work.

No wrappers are deleted and no legacy table is renamed. The seed inventory is not
an exhaustive claim about your local scripts or scheduled jobs.

See VALIDATION.md for the execution actually performed while creating this bundle.
