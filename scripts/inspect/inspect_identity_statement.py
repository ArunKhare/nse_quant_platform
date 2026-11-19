"""Inspect exact untrusted statement text; never authorize identity or ingest anything."""

from nse_quant.data_platform.identity_statement_inspect_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
