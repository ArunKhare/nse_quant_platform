# FS2a native Silver decoding

Reconstructed delivery from the implementation shown earlier in this conversation.
This is an implementation candidate, not locally integrated or production-certified.

## Protocol and dependency decision

Sources reviewed in the original implementation turn:
- https://kite.trade/docs/connect/v3/websocket/
- https://github.com/zerodha/pykiteconnect/blob/master/kiteconnect/ticker.py

The SDK reference was current master, not an immutable pinned commit. No SDK private
method is imported. Version kite-binary@1 independently implements unsigned big-endian
u16 frame count/length, u32 fields and u16 depth orders. Lengths: 8 LTP, 28/32 index,
44/184 non-index quote/full. Ten depth entries use quantity u32, raw price u32,
orders u16 and two ignored padding bytes. First five are bids; next five are offers.
Price divisors: segment 3 uses 10000000; segments 6/12 use 10000; recognized others
use 100. Unknown segments fail closed. Index change is preserved as raw bits, not
interpreted as signed, scaled or percentage change. Prices retain raw integer/divisor.
Timestamp fields are epoch seconds converted to aware UTC. Zero explicitly maps to
missing while original zero remains in raw fields. No receipt-time substitution.

## Whole-frame bounded policy

1 MiB frame limit, 4096 packet limit; these are service policies, not capacity claims.
Validate all framing and complete consumption. Any unsupported/malformed packet emits
no quote packets from that frame. No partial salvage. Zero-based packet ordinals,
length/payload offsets and sizes preserve location. One-byte binary payloads classify
as heartbeat/control. Text stays opaque without account JSON parsing or body logging.
Synthetic fixtures are not captured broker traffic or independent conformance proof.

## Persistence and availability

Read-only Bronze connection and separate dedicated single-owner Silver database.
Exact variant pinning; verify payload/envelope hashes and receipt identity. Never
update Bronze, choose a conflict winner or consult a legacy cache. Immutable frame
results/dispositions live in silver.kite_frames; typed packet dataclasses are serialized
as canonical nested JSON, not yet separate instrument-resolved relational observations.
Revision identity hashes receipt ID, envelope hash, payload hash and decoder version.
Exact retries compare deterministic output without replacing the first row. New decoder
versions coexist; same-version differences fail. All dispositions are persisted.

AuditLedger records execution with pinned-scope fingerprint and contract registration.
Explicit initialization bootstraps A1 then creates Silver objects within audited execution.
Domain insertion is transactional; audit completion is separate, so incomplete audit
must remain visible after crashes. Pre-open/input-validation failures cannot be audited
in a destination not yet available. No claim of process-crash recovery certification.

Receipt, Bronze recording, normalization, Silver recording, exchange-event and last-trade
times remain distinct. Recording timestamps are insertion clocks, not commit timestamps.
No publication occurs: published_at is null. This table alone does not implement
exact_decision_replay, as_known_at or research_recomputed. Future publication and decision
bundle ledgers must establish availability; future selection must resolve invalidations
before quality filtering. No fabricated historical publication or latest-version replay.

FS2b owns instrument-reference acquisition/versioning and contract resolution. Tokens
remain unresolved provider references. No IV/Greeks, eligibility, strategy, live broker
operations or decision-loop changes. Existing capture/Bronze/health/drain files untouched.
The available source snapshots showed old drain @1 despite newer capture health; reconcile
actual local HEAD, never downgrade the committed FS1c implementation.
