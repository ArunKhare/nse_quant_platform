"""End-to-end smoke tests for paper execution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nse_quant.execution.broker import PaperBroker
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.risk.risk_engine import RiskEngine
from tests.test_risk_and_execution import features, proposal


def test_end_to_end(tmp_path):
    store = DuckDBStore(tmp_path / "smoke.duckdb")
    p=proposal(); assert RiskEngine(store.conn).evaluate(p,features()).approved
    assert PaperBroker().submit(p).status.value=="FILLED"
    store.close()
