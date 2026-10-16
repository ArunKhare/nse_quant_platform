"""Canonical Pydantic models."""
from __future__ import annotations
from datetime import date,datetime,timezone
from enum import Enum
from typing import Any,Literal
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,field_validator

class OptionType(str,Enum): CE="CE"; PE="PE"
class OrderSide(str,Enum): BUY="BUY"; SELL="SELL"
class OrderStatus(str,Enum): CREATED="CREATED"; SUBMITTED="SUBMITTED"; FILLED="FILLED"; REJECTED="REJECTED"; CANCELLED="CANCELLED"
class MarketRegime(str,Enum): TREND_UP="TREND_UP"; TREND_DOWN="TREND_DOWN"; RANGE="RANGE"; VOLATILE="VOLATILE"; UNKNOWN="UNKNOWN"

class Instrument(BaseModel):
    model_config=ConfigDict(frozen=True)
    tradingsymbol:str; instrument_token:int; underlying:str; expiry:date; strike:float; option_type:OptionType; lot_size:int
    @field_validator("lot_size")
    @classmethod
    def positive(cls,v:int)->int:
        if v<=0: raise ValueError("lot_size must be positive")
        return v

class Quote(BaseModel):
    instrument_token:int; ltp:float|None=None; bid:float|None=None; ask:float|None=None; volume:int|None=None; oi:int|None=None
    exchange_ts:datetime|None=None; trade_ts:datetime|None=None; received_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))

class OptionQuote(Quote):
    instrument:Instrument; iv:float|None=None; delta:float|None=None; gamma:float|None=None; vega:float|None=None; theta:float|None=None
    @property
    def mid(self)->float|None:
        return (self.bid+self.ask)/2 if self.bid and self.ask and self.ask>=self.bid>0 else self.ltp
    @property
    def spread_pct(self)->float|None:
        return (self.ask-self.bid)/((self.ask+self.bid)/2) if self.bid and self.ask and self.ask>=self.bid>0 else None

class ChainSnapshot(BaseModel):
    run_id:str=Field(default_factory=lambda:uuid4().hex); ts:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    underlying:str; spot:float; expiry:date; quotes:list[OptionQuote]; is_market_open:bool=True
    def atm_strike(self)->float: return min(self.quotes,key=lambda q:abs(q.instrument.strike-self.spot)).instrument.strike

class MarketFeatures(BaseModel):
    ts:datetime; underlying:str; spot:float; expiry:date
    atm_iv:float|None=None; iv_rank:float|None=None; iv_percentile:float|None=None; realized_vol:float|None=None
    iv_rv_spread:float|None=None; pcr:float|None=None; total_call_oi:int|None=None; total_put_oi:int|None=None
    max_pain:float|None=None; liquidity_score:float|None=None; regime:MarketRegime=MarketRegime.UNKNOWN
    short_momentum:float|None=None; straddle_price:float|None=None; expected_move_pct:float|None=None
    expected_move_points:float|None=None; diagnostics:dict[str,Any]=Field(default_factory=dict)

class Leg(BaseModel):
    instrument:Instrument; side:OrderSide; lots:int
    @property
    def quantity(self)->int: return self.lots*self.instrument.lot_size

class TradeProposal(BaseModel):
    proposal_id:str=Field(default_factory=lambda:uuid4().hex); created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    strategy:str; underlying:str; expiry:date; thesis:str; legs:list[Leg]; entry_limit_price:float
    target_price:float|None=None; stop_loss_price:float|None=None; expected_move_points:float|None=None
    metadata:dict[str,Any]=Field(default_factory=dict)

class GateResult(BaseModel):
    gate:str; passed:bool; reason:str; details:dict[str,Any]=Field(default_factory=dict)

class RiskDecision(BaseModel):
    approved:bool; reasons:list[str]=Field(default_factory=list); checks:list[GateResult]=Field(default_factory=list)

class PaperOrder(BaseModel):
    order_id:str=Field(default_factory=lambda:uuid4().hex); proposal_id:str; strategy:str
    created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc)); status:OrderStatus=OrderStatus.CREATED
    legs:list[Leg]; limit_price:float; filled_price:float|None=None; filled_at:datetime|None=None; reject_reason:str|None=None

class PaperPosition(BaseModel):
    position_id:str=Field(default_factory=lambda:uuid4().hex); proposal_id:str; strategy:str; opened_at:datetime
    legs:list[Leg]; entry_price:float; current_price:float|None=None; realized_pnl:float=0; unrealized_pnl:float=0
    status:Literal["OPEN","CLOSED"]="OPEN"; exit_reason:str|None=None; closed_at:datetime|None=None; thesis:str=""
    thesis_status:Literal["ACTIVE","VALID","INVALID","EXPIRED"]="ACTIVE"; review_notes:str|None=None
