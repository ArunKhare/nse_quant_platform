"""Kite REST provider."""
from __future__ import annotations
from datetime import date,datetime,timezone
from typing import Any
from core.settings import settings
from market_data.chain import build_snapshot,discover_chain

class KiteMarketDataProvider:
    def __init__(self,kite:Any,underlying:str|None=None): self.kite=kite; self.underlying=underlying or settings.universe.underlying; self._instruments=None
    def refresh_instruments(self): self._instruments=self.kite.instruments("NFO")
    def get_spot(self)->float:
        key=f"NSE:{self.underlying} 50" if self.underlying=="NIFTY" else f"NSE:{self.underlying}"
        return float(self.kite.quote([key])[key]["last_price"])
    def get_chain_snapshot(self,expiry:date|None=None):
        if self._instruments is None: self.refresh_instruments()
        spot=self.get_spot(); exp,insts=discover_chain(self._instruments,self.underlying,spot,expiry,settings.universe.strikes_per_side)
        raw=self.kite.quote([f"NFO:{i.tradingsymbol}" for i in insts]); ticks={}
        for i in insts:
            q=raw.get(f"NFO:{i.tradingsymbol}",{}); depth=q.get("depth") or {}
            ticks[i.instrument_token]={"ltp":q.get("last_price"),"bid":(depth.get("buy") or [{}])[0].get("price"),"ask":(depth.get("sell") or [{}])[0].get("price"),"volume":q.get("volume"),"oi":q.get("oi"),"exchange_ts":q.get("exchange_timestamp"),"trade_ts":q.get("last_trade_time"),"received_at":datetime.now(timezone.utc)}
        return build_snapshot(self.underlying,spot,exp,insts,ticks)
