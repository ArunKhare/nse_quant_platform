"""Broker abstraction and paper broker."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from nse_quant.core.models import OrderStatus, PaperOrder, PaperPosition, TradeProposal


class BrokerInterface(ABC):
    @abstractmethod
    def submit(self,p:TradeProposal)->PaperOrder:...
    @abstractmethod
    def positions(self)->list[PaperPosition]:...

class PaperBroker(BrokerInterface):
    def __init__(self): self.orders=[]; self.positions=[]
    def submit(self,p:TradeProposal)->PaperOrder:
        o=PaperOrder(proposal_id=p.proposal_id,strategy=p.strategy,legs=p.legs,limit_price=p.entry_limit_price,status=OrderStatus.SUBMITTED)
        if p.entry_limit_price<=0: o.status=OrderStatus.REJECTED; o.reject_reason="invalid_price"
        else:
            o.status=OrderStatus.FILLED; o.filled_price=p.entry_limit_price; o.filled_at=datetime.now(UTC)
            self.positions.append(PaperPosition(proposal_id=p.proposal_id,strategy=p.strategy,opened_at=o.filled_at,legs=p.legs,entry_price=p.entry_limit_price,current_price=p.entry_limit_price,thesis=p.thesis))
        self.orders.append(o); return o
    def positions(self): return list(self.positions)
    def close_position(self,pid:str,exit_price:float,reason:str):
        for pos in self.positions:
            if pos.position_id==pid and pos.status=="OPEN":
                pos.status="CLOSED"; pos.exit_reason=reason; pos.closed_at=datetime.now(UTC); pos.current_price=exit_price
                pos.realized_pnl=(pos.entry_price-exit_price)*25; pos.thesis_status="VALID" if pos.realized_pnl>=0 else "INVALID"; return pos
        return None
