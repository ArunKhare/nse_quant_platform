"""Audited immutable bundle staging entry point, explicitly not publication."""

from nse_quant.data_platform.quote_bundle_stage_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
