"""Canonical Pydantic models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class MarketRegime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)
    tradingsymbol: str
    instrument_token: int
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    lot_size: int

    @field_validator("lot_size")
    @classmethod
    def positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("lot_size must be positive")
        return v


class Quote(BaseModel):
    instrument_token: int
    ltp: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    oi: int | None = None
    exchange_ts: datetime | None = None
    trade_ts: datetime | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OptionQuote(Quote):
    instrument: Instrument
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None

    @property
    def mid(self) -> float | None:
        return (
            (self.bid + self.ask) / 2
            if self.bid and self.ask and self.ask >= self.bid > 0
            else self.ltp
        )

    @property
    def spread_pct(self) -> float | None:
        return (
            (self.ask - self.bid) / ((self.ask + self.bid) / 2)
            if self.bid and self.ask and self.ask >= self.bid > 0
            else None
        )


class ChainSnapshot(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    underlying: str
    spot: float
    expiry: date
    quotes: list[OptionQuote]
    is_market_open: bool = True

    def atm_strike(self) -> float:
        return min(
            self.quotes, key=lambda q: abs(q.instrument.strike - self.spot)
        ).instrument.strike

    @property
    def snapshot_date(self) -> date:
        return self.ts.date()


class MarketFeatures(BaseModel):
    ts: datetime
    underlying: str
    spot: float
    expiry: date
    atm_iv: float | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    realized_vol: float | None = None
    iv_rv_spread: float | None = None
    iv_analytics: IVAnalytics | None = None
    pcr: float | None = None
    total_call_oi: int | None = None
    total_put_oi: int | None = None
    max_pain: float | None = None
    liquidity_score: float | None = None
    regime: MarketRegime = MarketRegime.UNKNOWN
    short_momentum: float | None = None
    straddle_price: float | None = None
    expected_move_pct: float | None = None
    expected_move_points: float | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class IVAnalytics(BaseModel):
    current_iv: float | None = None
    iv_min: float | None = None
    iv_max: float | None = None
    valid_history_count: int = 0
    iv_rank: float | None = None
    iv_percentile: float | None = None
    calculation_version: str = "v2"


class Leg(BaseModel):
    instrument: Instrument
    side: OrderSide
    lots: int
    entry_price: float | None = None

    @property
    def quantity(self) -> int:
        return self.lots * self.instrument.lot_size

    @property
    def signed_quantity(self):
        return self.quantity if self.side == OrderSide.BUY else -self.quantity


class TradeProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy: str
    underlying: str
    expiry: date
    thesis: str
    legs: list[Leg]
    entry_limit_price: float
    target_price: float | None = None
    stop_loss_price: float | None = None
    expected_move_points: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateResult(BaseModel):
    gate: str
    passed: bool
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(BaseModel):
    approved: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[GateResult] = Field(default_factory=list)


class PaperOrder(BaseModel):
    order_id: str = Field(default_factory=lambda: uuid4().hex)
    proposal_id: str
    strategy: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: OrderStatus = OrderStatus.CREATED
    legs: list[Leg]
    limit_price: float
    filled_price: float | None = None
    filled_at: datetime | None = None
    reject_reason: str | None = None


class StrategyPositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ExitReason(StrEnum):
    MANUAL_KILL_SWITCH = "MANUAL_KILL_SWITCH"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"
    EXPIRY_FORCE_CLOSE = "EXPIRY_FORCE_CLOSE"
    STOP_LOSS = "STOP_LOSS"
    TARGET_PROFIT = "TARGET_PROFIT"
    THETA_DECAY_TARGET = "THETA_DECAY_TARGET"
    IV_COLLAPSE = "IV_COLLAPSE"
    EXPECTED_MOVE_VIOLATION = "EXPECTED_MOVE_VIOLATION"
    DATA_QUALITY_EXIT = "DATA_QUALITY_EXIT"


EXIT_PRIORITY: list[ExitReason] = [
    ExitReason.MANUAL_KILL_SWITCH,
    ExitReason.RISK_LIMIT_BREACH,
    ExitReason.EXPIRY_FORCE_CLOSE,
    ExitReason.STOP_LOSS,
    ExitReason.TARGET_PROFIT,
    ExitReason.THETA_DECAY_TARGET,
    ExitReason.IV_COLLAPSE,
    ExitReason.EXPECTED_MOVE_VIOLATION,
    ExitReason.DATA_QUALITY_EXIT,
]


class StrategyPosition(BaseModel):
    strategy_position_id: str = Field(default_factory=lambda: uuid4().hex)
    proposal_id: str
    strategy: str
    underlying: str
    expiry: date
    opened_at: datetime
    status: StrategyPositionStatus = StrategyPositionStatus.OPEN
    entry_price: float
    current_price: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    exit_reason: ExitReason | None = None
    all_triggered_exits: list[ExitReason] = Field(default_factory=list)
    closed_at: datetime | None = None
    thesis: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegPosition(BaseModel):
    leg_position_id: str = Field(default_factory=lambda: uuid4().hex)
    strategy_position_id: str
    proposal_id: str
    strategy: str
    instrument: Instrument
    side: OrderSide
    lots: int
    opened_at: datetime
    entry_price: float
    current_price: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    status: StrategyPositionStatus = StrategyPositionStatus.OPEN
    closed_at: datetime | None = None
    exit_reason: ExitReason | None = None
    mark_stale: bool = False

    @property
    def quantity(self) -> int:
        return self.lots * self.instrument.lot_size

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.side == OrderSide.BUY else -self.quantity


class ExitEvaluation(BaseModel):
    strategy_position_id: str
    evaluated_at: datetime
    triggered_reasons: list[ExitReason]
    selected_reason: ExitReason | None
    details: dict[str, Any] = Field(default_factory=dict)


class PostTradeReview(BaseModel):
    review_id: str = Field(default_factory=lambda: uuid4().hex)
    strategy_position_id: str
    proposal_id: str
    strategy: str
    closed_at: datetime
    realized_pnl: float
    exit_reason: ExitReason
    thesis_status: Literal["VALID", "INVALID", "EXPIRED", "UNKNOWN"] = "UNKNOWN"
    decision_quality_notes: str = ""
    outcome_notes: str = ""


class PaperPosition(BaseModel):
    position_id: str = Field(default_factory=lambda: uuid4().hex)
    proposal_id: str
    strategy: str
    opened_at: datetime
    legs: list[Leg]
    entry_price: float
    current_price: float | None = None
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    status: Literal["OPEN", "CLOSED"] = "OPEN"
    exit_reason: str | None = None
    closed_at: datetime | None = None
    thesis: str = ""
    thesis_status: Literal["ACTIVE", "VALID", "INVALID", "EXPIRED"] = "ACTIVE"
    review_notes: str | None = None
    leg_entry_prices: dict[int, float] = Field(default_factory=dict)
    leg_current_prices: dict[int, float] = Field(default_factory=dict)
