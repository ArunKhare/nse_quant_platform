# Risk and safety

Defaults: `DRY_RUN=true`, `TRADING_ENABLED=false`, `PAPER_TRADING=true`. Risk limits are centralized in YAML and validated at startup. The persistent kill switch blocks order creation. Future live mode requires reconciliation, margin checks, and explicit removal of the milestone-level live-trading block.
