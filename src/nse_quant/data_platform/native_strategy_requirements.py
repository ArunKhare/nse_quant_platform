"""Source-reconciled proposal input inventory; not native strategy implementation/readiness."""

from __future__ import annotations

import hashlib
import json

VERSION = "iron-condor-proposal-input-requirements@1"
STRATEGY = "iron_condor_monitor"
# Direct proposal/evaluator scope only. This is NOT complete paper-loop/risk input coverage.
REQUIREMENTS: tuple[tuple[str, str, str], ...] = (
    (
        "chain_time_expiry_spot",
        "strategy/iron_condor.py:evaluate",
        "chain.ts,expiry,spot and ATM strike selection; expiry date is not validity proof",
    ),
    (
        "option_chain_and_contract_terms",
        "strategy/iron_condor.py:evaluate,_select_long_quote,_leg",
        "full candidate CE/PE strikes, expiry, instrument terms, lot quantities, LTP/mid/bid/ask",
    ),
    ("market_session", "strategy/gates.py:MarketOpenGate", "snapshot.is_market_open"),
    (
        "iv_rank_and_history",
        "strategy/gates.py:IvRegimeGate",
        "nullable IV rank and observation count; effective cold-start policy is explicit",
    ),
    ("iv_rv_spread", "strategy/gates.py:IvRegimeGate", "IV-RV spread and threshold"),
    (
        "expected_move",
        "strategy/gates.py:ExpectedMoveGate",
        "positive expected_move_points; diagnostic inputs retained separately",
    ),
    (
        "candidate_liquidity",
        "strategy/gates.py:LiquidityGate",
        "CE AND PE at every selected strike; OI/volume/spread; missing depth/low volume warnings",
    ),
    (
        "effective_proposal_configuration",
        "strategy/iron_condor.py;strategy/gates.py",
        "wing distance,minimum credit,analytics thresholds/history/cold-start and liquidity limits",
    ),
    (
        "authoritative_identity_and_time",
        "native medallion acceptance boundary",
        "canonical instrument binding and independently evidenced knowledge/economic validity",
    ),
)
DEFINITION_SHA256 = hashlib.sha256(
    json.dumps([VERSION, STRATEGY, REQUIREMENTS], separators=(",", ":")).encode()
).hexdigest()
STAGES = (
    "kill_switch",
    "safety_boundary",
    "publication_admission",
    "native_inputs",
    "strategy",
    "portfolio_risk",
    "execution",
)
