"""Native Gold quote build entry point; never a migration/publication command."""

from nse_quant.data_platform.gold_quote_build_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
