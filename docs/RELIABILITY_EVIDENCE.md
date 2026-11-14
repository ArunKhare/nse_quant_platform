# Multi-complete-trading-day reliability evidence

`src/nse_quant/research/reliability_evidence.py` is a pure additive evaluator that aggregates per-trading-day paper-loop reliability records into a single reliability summary.

## Contract

- Input: list of `TradingDayRecord` (trading_day, cycles_run, cycles_passed, evidence_complete, kill_switch_triggered, errors) plus optional `ReliabilitySettings`.
- Output: dict with status, totals, pass_rate, failures list, settings echo, and `decision_eligibility_asserted=False`.
- `summarize_reliability(records)` returns a lighter totals-only view.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every record, evaluation, and summary.
- Failure modes: insufficient days, insufficient cycles, cycles not all passed, errors exceeded, evidence incomplete, kill switch triggered (unless explicitly allowed).
