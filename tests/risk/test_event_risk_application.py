"""Tests for event-risk proposal application."""

from __future__ import annotations

from datetime import date

from nse_quant.core.models import (
    Instrument,
    Leg,
    OptionType,
    OrderSide,
    TradeProposal,
)
from nse_quant.risk.event_risk_application import apply_event_risk_to_proposal
from nse_quant.risk.event_risk_policy import EventRiskDecision


def build_proposal(lots: int = 2) -> TradeProposal:
    instrument = Instrument(
        tradingsymbol="NIFTY25OCT23000CE",
        instrument_token=1,
        underlying="NIFTY",
        expiry=date(2026, 10, 29),
        strike=23000.0,
        option_type=OptionType.CE,
        lot_size=75,
    )
    return TradeProposal(
        strategy="iron_condor",
        underlying="NIFTY",
        expiry=date(2026, 10, 29),
        thesis="test",
        legs=[Leg(instrument=instrument, side=OrderSide.SELL, lots=lots)],
        entry_limit_price=100.0,
    )


def test_block_new_entries_returns_none():
    decision = EventRiskDecision(action="BLOCK_NEW_ENTRIES", size_multiplier=0.0)
    assert apply_event_risk_to_proposal(build_proposal(), decision) is None


def test_full_multiplier_returns_original_proposal():
    proposal = build_proposal()
    decision = EventRiskDecision(action="OBSERVE", size_multiplier=1.0)
    assert apply_event_risk_to_proposal(proposal, decision) is proposal


def test_reduction_scales_lots_with_floor_of_one():
    proposal = build_proposal(lots=2)
    decision = EventRiskDecision(action="REDUCE_SIZE", size_multiplier=0.5)
    reduced = apply_event_risk_to_proposal(proposal, decision)
    assert reduced is not None
    assert reduced.legs[0].lots == 1


def test_reduction_never_zeroes_lots():
    proposal = build_proposal(lots=1)
    decision = EventRiskDecision(action="REDUCE_SIZE", size_multiplier=0.5)
    reduced = apply_event_risk_to_proposal(proposal, decision)
    assert reduced is not None
    assert reduced.legs[0].lots == 1
