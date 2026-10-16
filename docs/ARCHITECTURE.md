# Architecture

`Kite -> TickNormalizer -> ChainSnapshot -> Analytics -> Gates -> Strategy -> RiskEngine -> PaperBroker -> PositionTracker -> DuckDB`

All deployment tunables are centralized in `config/settings.yaml`; secrets remain in `.env`; immutable domain constants remain in `core/constants.py`. Strategies emit proposals only; risk independently approves or rejects; execution performs state transitions.
