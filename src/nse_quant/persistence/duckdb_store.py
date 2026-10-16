"""DuckDB persistence."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import duckdb
from core.models import ChainSnapshot,TradeProposal
from core.settings import settings

class DuckDBStore:
    def __init__(self,path:str|Path|None=None):
        self.path=Path(path or settings.storage.db_path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.conn=duckdb.connect(str(self.path)); self._schema()
    def _schema(self):
        self.conn.execute("""CREATE TABLE IF NOT EXISTS option_stream(run_id VARCHAR,ts TIMESTAMPTZ,underlying VARCHAR,expiry DATE,strike DOUBLE,option_type VARCHAR,tradingsymbol VARCHAR,instrument_token BIGINT,lot_size INTEGER,spot DOUBLE,ltp DOUBLE,bid DOUBLE,ask DOUBLE,volume BIGINT,oi BIGINT,iv DOUBLE,delta DOUBLE,gamma DOUBLE,vega DOUBLE,theta DOUBLE,quote_status VARCHAR,payload_json JSON)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS decision_events(event_id VARCHAR,ts TIMESTAMPTZ,run_id VARCHAR,event_type VARCHAR,strategy VARCHAR,underlying VARCHAR,expiry DATE,proposal_json JSON,decision_json JSON,reason VARCHAR)""")
    def write_option_stream(self,run_id:str,snapshot:ChainSnapshot,ticks:dict[int,dict[str,Any]])->int:
        rows=[]
        for q in snapshot.quotes:
            t=ticks.get(q.instrument_token,{})
            rows.append((run_id,snapshot.ts,snapshot.underlying,snapshot.expiry,q.instrument.strike,q.instrument.option_type.value,q.instrument.tradingsymbol,q.instrument_token,q.instrument.lot_size,snapshot.spot,t.get("ltp",q.ltp),t.get("bid",q.bid),t.get("ask",q.ask),t.get("volume",q.volume),t.get("oi",q.oi),q.iv,q.delta,q.gamma,q.vega,q.theta,"ready" if t else "missing",json.dumps(t,default=str)))
        if rows: self.conn.executemany("INSERT INTO option_stream VALUES ("+",".join(["?"]*22)+")",rows)
        return len(rows)
    def write_event(self,event_type:str,run_id:str,proposal:TradeProposal|None=None,decision:Any=None,reason:str|None=None)->str:
        eid=uuid4().hex
        self.conn.execute("INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?,?,?)",(eid,datetime.now(timezone.utc),run_id,event_type,proposal.strategy if proposal else None,proposal.underlying if proposal else None,proposal.expiry if proposal else None,proposal.model_dump_json() if proposal else None,json.dumps(decision,default=str) if decision is not None else None,reason))
        return eid
    def latest_iv_history(self,underlying:str,limit:int|None=None)->list[float]:
        limit=limit or settings.analytics.iv_history_limit
        rows=self.conn.execute("SELECT avg(iv) FROM (SELECT ts,avg(iv) atm_iv FROM option_stream WHERE underlying=? AND iv IS NOT NULL GROUP BY ts ORDER BY ts DESC LIMIT ?) GROUP BY ts ORDER BY ts",[underlying,limit]).fetchall()
        return [float(r[0]) for r in rows]
    def export_parquet(self,out_dir:str|Path,date_str:str)->Path:
        out=Path(out_dir)/f"option_stream_{date_str}.parquet"; out.parent.mkdir(parents=True,exist_ok=True)
        self.conn.execute("COPY (SELECT * FROM option_stream WHERE CAST(ts AS DATE)=?) TO ? (FORMAT PARQUET)",[date_str,str(out)]); return out
    def close(self): self.conn.close()
