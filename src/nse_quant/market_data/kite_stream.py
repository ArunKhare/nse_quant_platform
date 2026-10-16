"""Read-only bounded Kite WebSocket runner."""
from __future__ import annotations
import argparse,json,os,tempfile,threading,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from core.settings import settings
from market_data.kite_provider import KiteMarketDataProvider
from market_data.normalizer import normalize_tick
from persistence.duckdb_store import DuckDBStore

def atomic_write(path:Path,payload:dict[str,Any]):
    path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,"w") as h: json.dump(payload,h,default=str)
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--seconds",type=int,default=120); args=parser.parse_args()
    from kiteconnect import KiteTicker
    from kite_auth import get_authenticated_kite
    kite=get_authenticated_kite(); provider=KiteMarketDataProvider(kite); snap=provider.get_chain_snapshot()
    tokens=sorted({q.instrument_token for q in snap.quotes}); state={}; lock=threading.Lock(); connected=threading.Event()
    ws=KiteTicker(settings.secrets.kite_api_key,kite.access_token)
    ws.on_connect=lambda c,r:(c.subscribe(tokens),c.set_mode(c.MODE_FULL,tokens),connected.set())
    def on_ticks(c,ticks):
        now=datetime.now(timezone.utc)
        with lock:
            for t in ticks: state[int(t["instrument_token"])]=normalize_tick(t,now).model_dump(mode="json")
    ws.on_ticks=on_ticks; ws.on_error=lambda *a:connected.clear(); ws.on_close=lambda *a:connected.clear()
    store=DuckDBStore(); run_id=uuid.uuid4().hex; ws.connect(threaded=True); end=time.monotonic()+args.seconds
    try:
        while time.monotonic()<end:
            time.sleep(1)
            with lock: current=dict(state)
            store.write_option_stream(run_id,snap,current)
            atomic_write(Path("market_data/latest_stream.json"),{"run_id":run_id,"connected":connected.is_set(),"ticks":len(current)})
    except KeyboardInterrupt: pass
    finally:
        ws.close(); store.close()
    return 0

if __name__=="__main__": raise SystemExit(main())
