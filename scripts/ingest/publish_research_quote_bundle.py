"""Explicit research-only bundle publication entry point. Never decision admission."""

from nse_quant.data_platform.quote_publication_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
