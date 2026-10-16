"""Paper decision loop."""
from __future__ import annotations
import argparse,time,uuid
from analytics.features import build_features
from core.settings import settings
from execution.paper_broker import PaperBroker
from market_data.kite_provider import KiteMarketDataProvider
from ops.kill_switch import KillSwitch
from ops.notifier import Notifier
from persistence.duckdb_store import DuckDBStore
from risk.risk_engine import RiskEngine
from strategy.iron_condor import IronCondorMonitor

def run_once(provider,store,broker,risk,run_id)->dict:
    snap=provider.get_chain_snapshot(); features=build_features(snap,store.latest_iv_history(snap.underlying),[snap.spot]*30)
    store.write_event("feature_snapshot",run_id,decision=features.model_dump(mode="json"))
    proposal,gates=IronCondorMonitor().evaluate(snap,features)
    if proposal is None: return {"status":"no_proposal"}
    store.write_event("signal",run_id,proposal,{"gates":[g.model_dump() for g in gates]})
    lookup={(q.instrument.option_type.value,q.instrument.strike):q for q in snap.quotes}
    decision=risk.evaluate(proposal,features,lookup); store.write_event("risk_decision",run_id,proposal,decision.model_dump(),",".join(decision.reasons))
    if not decision.approved: return {"status":"risk_rejected","reasons":decision.reasons}
    if settings.safety.dry_run or not settings.safety.trading_enabled:
        store.write_event("dry_run_order_skipped",run_id,proposal,{"would_submit":True},"DRY_RUN"); return {"status":"dry_run","proposal_id":proposal.proposal_id}
    order=broker.submit(proposal); store.write_event("paper_order",run_id,proposal,order.model_dump(mode="json"),order.status.value)
    if order.status==OrderStatus.FILLED: risk.register_fill(proposal,order.filled_price or 0)
    return {"status":order.status.value,"proposal_id":proposal.proposal_id}

from core.models import OrderStatus

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--seconds",type=int,default=120); parser.add_argument("--config",default=None); args=parser.parse_args()
    from kite_auth import get_authenticated_kite
    kite=get_authenticated_kite(); provider=KiteMarketDataProvider(kite); store=DuckDBStore(); broker=PaperBroker(); risk=RiskEngine(); kill=KillSwitch(); notifier=Notifier(); run_id=uuid.uuid4().hex; end=time.monotonic()+args.seconds
    try:
        while time.monotonic()<end:
            if kill.is_active(): store.write_event("kill_switch_active",run_id,reason="orders blocked"); break
            result=run_once(provider,store,broker,risk,run_id); print(result)
            if result["status"] in {"risk_rejected","dry_run"}: notifier.send(f"NSE Quant: {result['status']} {result.get('reasons','')}")
            time.sleep(settings.runtime.loop_interval_seconds)
    except KeyboardInterrupt: pass
    finally: store.close()
    return 0

if __name__=="__main__": raise SystemExit(main())
