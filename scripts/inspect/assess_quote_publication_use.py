"""Read-only purpose admission assessment, not a trading or migration entry point."""

from nse_quant.data_platform.publication_admission_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
