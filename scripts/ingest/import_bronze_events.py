"""Explicit, audited import into a dedicated Bronze database; planning is default."""

from nse_quant.data_platform.bronze_import import main

if __name__ == "__main__":
    raise SystemExit(main())
