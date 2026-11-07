# Native portfolio-risk evaluation

`evaluate_portfolio_risk` evaluates a trade proposal against portfolio-level limits.

## Contract

- Input: proposal dict (underlying, notional), open_positions list, `PortfolioRiskSettings`.
- Output: `PortfolioRiskDecision` with approved, reasons, checks.
- Safety: never places, modifies, or cancels orders; never bypasses the kill switch.

## Rules

- Rejects invalid proposal/underlying/notional.
- Checks max_open_positions, max_notional_exposure, max_concentration_pct.
- Concentration is per-underlying notional as a percentage of total notional.
