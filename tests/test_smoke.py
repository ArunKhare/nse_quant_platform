from tests.test_risk_and_execution import features,proposal
from execution.paper_broker import PaperBroker
from risk.risk_engine import RiskEngine

def test_end_to_end():
    p=proposal(); assert RiskEngine().evaluate(p,features()).approved
    assert PaperBroker().submit(p).status.value=="FILLED"
