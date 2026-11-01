"""Thin offline instrument-reference entry point; no broker operations."""

from nse_quant.data_platform.instrument_reference_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
