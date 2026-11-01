"""Audited admission-input capture entry point; never a trading command."""

from nse_quant.data_platform.admission_capture_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
