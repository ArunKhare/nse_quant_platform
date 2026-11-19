# FS2b1 offline instrument-reference evidence: reconstructed delivery

This archive reconstructs the FS2b1 package from this conversation. It is NOT a recovered
copy of your current local HEAD or a byte-identical copy of the original ZIP. Compare
with local committed files; never overwrite an existing implementation to match this
archive. Reconstructed tests/docs are new delivery artifacts, not proof of old QA.

## Original policy boundary

Parser kite-instruments-csv@1; resolver pinned-token-reference@1; contract/schema 1.
Offline source kite_instruments_offline, format kite_instruments_csv_utf8, origin
historical_import. Exact supplied FILE bytes are stored as Bronze event payload and
input artifact in an audited bounded batch. Receipt time is actual local import time,
not an invented original HTTP/provider receipt. Original provider receipt/publication,
economic effective interval and platform publication remain unknown/null in Silver.

Explicit session+record identity. Exact retry reuses first import receipt time and
appends no event variant. Changed content gets actual new import time and appends a
conflict variant; CLI reports conflicts. Existing multi-variant identity blocks further
imports pending review. No source evidence deletion or silent conflict winner.

Strict UTF-8/BOM CSV, documented ordered columns, header whitespace stripped only.
Bounded 16 MiB file, 200000 rows, 4096 characters per field. All-or-nothing parsing;
malformed data creates a whole-snapshot quarantine. No salvage or raw diagnostic logs.
Exact numeric decimal strings, no float conversion. Row ordinals count CSV data records,
not physical lines. Hashes of parsed field strings are not hashes of original CSV slices.
Duplicates remain duplicates: token lookup is ambiguous, never first/last-wins.

## Known v1 limitation: do not hide it

The original OFFLINE v1 parser requires nonempty decimal price/strike/tick fields and
positive lot size. Blank strike therefore quarantines, including provider rows that
legitimately omit it. This archive deliberately does NOT silently change an immutable
parser version's semantics or substitute zero. FS2b3 uses a DIFFERENT explicit native
CSV version that supports nullable fields. A reviewed offline parser v2/consolidation
would be separate work, preserve old results, and add proper fixtures. Do not use this
reconstructed v1 archive to replace that newer policy or downgrade local improvements.

## Silver and pinned lookup

Dedicated separate Silver DuckDB; objects qualified/quoted catalog.schema.table.
Immutable silver.instrument_reference_snapshots retain lineage and all dispositions.
Revision hashes receipt ID, envelope hash, payload hash and parser version. Same
input/version compares deterministic content and retains the first row; new versions
coexist. No UPDATE/REPLACE in the domain writer. AuditLedger jobs and dataset contract
registration follow inspected A1 interfaces; actual integration remains locally tested.

Source-reverified lookup pins an exact stored revision, validates original Bronze
hashes and canonical normalized content, then returns matched/ambiguous/unresolved
and row ordinals only. Provider names are not inferred underlyings; tokens are unresolved
provider references, never timeless canonical contract IDs. PINNED_SNAPSHOT_ONLY is
not historical validity, as_known_at, exact_decision_replay, a published reference bundle
or decision eligibility. Future consumers must resolve invalidations before quality
filtering and preserve true availability/recording/publication clocks.

No network, SDK instruments calls, token refresh, strategy, IV/Greeks, decision-loop
cutover or modifications to FS2a/FS2b2/FS2b3 are part of this reconstructed package.
Domain insertion and A1 finalization are separate; an incomplete audit must never be
manufactured successful after crash. No process-crash or production readiness claim.
