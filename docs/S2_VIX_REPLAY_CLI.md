# S2 VIX replay CLI — manual and read-only

This adds an invocation/reporting boundary around the committed
india_vix_recording.replay_vix_silver API. It does not implement a second verifier
or treat CLI boundary tests as proof of the entire persistence pipeline.

## Invocation

From the checkout's configured Python environment:

    python -m nse_quant.data_platform.india_vix_replay_cli --help
    python -m nse_quant.data_platform.india_vix_replay_cli \
      --bronze-db /absolute/path/to/bronze.duckdb \
      --silver-db /absolute/path/to/silver.duckdb \
      --revision-id <externally-reviewed-64-lowercase-hex-Silver-revision>

There is deliberately no capture, initialize, promote, repair, write-report,
latest-revision auto-selection, --apply, or scheduling option on this CLI.
No current-time/as_of override is accepted: replay uses the original policy
retained in Silver. The report does not assert that an old observation is fresh
for a current trading decision. Both source stores must already exist.

## Exit and report contract

- 0: verified_valid_observation. Replay verified the retained evidence and
  reproduced a valid observational VIX result under its original policy.
- 3: verified_rejected_evidence. Replay verified a retained rejection result;
  observation is null. This is NOT a successful or usable VIX observation.
- 2: verification_failed for path/open/replay/output-contract failures. JSON goes
  to stderr; stdout is empty. argparse usage errors also exit 2, using argparse's
  normal usage text rather than the replay report envelope.

Verified reports go to stdout and contain report_version, status,
replay_verified, revision_id, quality_state, rejection_reason, observation, and
an explicit decision_eligibility_asserted=false. Normalized observation fields
are allowlisted. Unknown fields/raw payloads are not included. Runtime failures
use a fixed error code without exception messages or database paths.

Do not treat exit 3 as permission to fall back, splice histories, or admit a
strategy. Exit 0 likewise confers no execution or decision authority.

## Resource and read-only behavior

The CLI strictly resolves existing regular files before connecting. Same-file,
symlink-alias and hardlink-alias Bronze/Silver targets are rejected. It opens
both DuckDB connections with read_only=True and closes them on success/failure,
including failure opening the second connection. It invokes only the existing
replay API; it does not call a provider, initialize a store, or write audit jobs.

No database files are created for missing paths. Reports are emitted to streams
only. User-directed shell redirection is outside this command's implementation.
Concurrent writers and DuckDB handle-configuration conflicts are not healed: a
locked/incompatible database causes failure, not a retry in write mode.

The current recording API remains the source-integrity/normalization authority.
This wrapper does not expand its trust guarantees or supply missing calendar,
EOD, roll-quality, historical-validity, or Black-76 surface evidence.

## Validation scope

The separate boundary selection uses real temporary DuckDB files, read-only
handles and byte-hash checks, with the replay adapter stubbed. Three additional
integration cases use the existing committed recording test fixtures: valid,
rejected and tampered evidence. Those cases must run in the real checkout.
Stage 1 and S2 remain IN PROGRESS.
