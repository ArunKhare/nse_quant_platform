# S2 native VIX durable inputs — bounded candidate increment

Status: Stage 1 and S2 IN PROGRESS. No activation or decision authority.

## Connection and audit ownership

Application caller exclusively owns each writer DuckDB connection and serializes
all operations. Pass an explicit writer_owner, used as AuditLedger actor_id, and
a reviewed 40-character code_revision. No ambient transactions or concurrent
writers. Writer functions do not close caller connections. Initialization is
explicit; readers never initialize stores. Bronze and Silver must be separate
dedicated files. Close writer handles before reopening read-only handles; never
mix incompatible DuckDB connection configurations to the same file.

This is an application ownership contract, not a database permission boundary.
Use the existing deployment single-writer supervision and DuckDB file locks.

AuditLedger owns audit lifecycle commits; BronzeEventStore owns Bronze batch
transactions. Silver context/record/attempt writes share one domain transaction.
No cross-database atomic transaction is asserted. A crash after a domain commit
but before successful audit completion leaves an unverified original recording.
Retry refuses to heal it; preserve the files for explicit reconciliation.

## API sequence (manual, opt-in only)

1. Explicitly initialize a dedicated Bronze store with initialize_vix_bronze.
2. Obtain RawVixCapture through the existing provider only when separately
   authorized. The persistence module itself never calls the network.
3. preserve_vix_capture(conn, capture, capture_session_id=..., source_record_id=...,
   writer_owner=..., code_revision=...). Persist the returned pins outside the DB.
4. Close the Bronze writer. Open Bronze read_only=True and separately open the
   Silver writer. Explicitly initialize_vix_silver on a dedicated Silver file.
5. observe_vix_bronze(bronze, pins=..., as_of=...) returns (context_bytes, record_bytes).
   Review the context and compute hashlib.sha256(context_bytes).hexdigest().
6. persist_vix_silver(bronze, silver, pins=..., as_of=the_same_instant,
   expected_context_sha256=reviewed_hash, writer_owner=..., code_revision=...).
   Retain the returned revision_id outside the DB as the replay pin.
7. Close writers. Open both stores read_only=True. replay_vix_silver(bronze, silver,
   revision_id=...) verifies source linkage and reproduces context and record bytes.

Never choose a fresh as_of during replay: its original value and freshness policy
are retained in Silver. Freshness is an original-observation property, not proof
that an old record is current. No session calendar, EOD, historical-validity,
monthly-roll quality or publication authority is asserted.

## Identity and retry policy

Use the same capture_session_id/source_record_id only for the SAME request.
A new request must have a new receipt identity, even if the price is unchanged.
The whole RawVixCapture is retained, including response JSON, instrument-reference
JSON, claimed hashes, request time and receive time. These are exact retained
JSON strings from the provider, NOT HTTP wire bytes. Source timestamps remain
unaltered in the raw response. Bronze recorded_at is an independent store clock.
No exchange timestamp is asserted for an unvalidated response.

Bronze batch key is the envelope hash. Exact retry uses native already_committed
semantics and creates an additional audit attempt, but does not duplicate data or
change the original recording fingerprint. Changed content under the same event
identity is retained as an alternative variant. Both variants are quarantined:
no Silver promotion or replay succeeds while that event is conflicted.

Silver revision is content-derived from the reviewed context. Exact verified retry
returns the existing revision without new Silver rows or a new audit job. No
same-revision overwrite or automatic repair occurs.

Malformed, invalid or stale source evidence is retained in Bronze. Silver may
retain a rejected normalization result with observation=null, a bounded reason,
and decision_eligibility_asserted=False; it is never a valid VIX observation.
Malformed capture envelope types, naive envelope clocks or excessive payloads
are request-contract failures and are not promised durable acceptance.

## Integrity and limitations

Replay checks retained envelope, payload hash, artifact bytes, original batch,
successful original audit, context hash, record hash, revision and re-normalized
output. Store files must be kept with externally reviewed pins and protected by
normal filesystem controls; hashes are not signatures or a defense against an
attacker authorized to rewrite all evidence and its external trust anchors.

India VIX records use only india_vix Silver tables; no internal_cm series is
spliced, relabeled or published. No operational database is opened by module
import, installation or replay. Broker and decision modules are not imported.

## Deferred

Surface evidence recording is NOT implemented here. Persisted option batches do
not by themselves supply a retained forward/rate/expiry-close/calendar evidence
bundle. Hash/reference strings alone do not establish exact Black-76 replay.
Full-cycle paper validation and wider S1–S6 acceptance remain outstanding.
