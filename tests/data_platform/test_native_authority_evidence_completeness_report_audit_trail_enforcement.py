import hashlib
import json

import pytest

from nse_quant.data_platform.native_authority_evidence_completeness_report_audit_trail_enforcement import (
    LIFECYCLE_STAGES,
    VERSION,
    enforce_authority_evidence_completeness_report_audit_trail,
)
from nse_quant.data_platform.native_strategy_input_coverage import Rejected


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _retained(obligations=None, healed=False):
    audit_trail = {
        "healed": healed,
        "report": {
            "obligations": obligations
            if obligations is not None
            else ["original_first_write", "audit", "orphan_check", "final_audit"]
        },
    }
    envelope = {"audit_trail": audit_trail}
    return {
        "version": VERSION,
        "point_in_time_decision": False,
        "decision_eligibility_asserted": False,
        "retained": envelope,
        "governance_fingerprint": hashlib.sha256(_canonical(envelope)).hexdigest(),
    }


def test_enforces_complete_retained_audit_trail():
    result = enforce_authority_evidence_completeness_report_audit_trail(_retained())
    assert result["enforcement_completed"] is True
    assert result["version"] == VERSION
    assert result["decision_eligibility_asserted"] is False
    enforced = result["enforced"]
    assert enforced["complete"] is True
    assert enforced["missing_obligations"] == []
    assert enforced["audit_integrated"] is True
    assert enforced["orphan_check_integrated"] is True
    assert enforced["final_audit_integrated"] is True
    assert enforced["lifecycle_stages"] == list(LIFECYCLE_STAGES)
    assert enforced["healed"] is False
    assert result["enforcement_fingerprint"] == hashlib.sha256(_canonical(enforced)).hexdigest()


def test_reports_exact_missing_obligations_without_integration():
    result = enforce_authority_evidence_completeness_report_audit_trail(_retained(["original_first_write", "audit"]))
    assert result["enforcement_completed"] is True
    enforced = result["enforced"]
    assert enforced["complete"] is False
    assert enforced["missing_obligations"] == ["orphan_check", "final_audit"]
    assert enforced["audit_integrated"] is True
    assert enforced["orphan_check_integrated"] is False
    assert enforced["final_audit_integrated"] is False
    assert result["decision_eligibility_asserted"] is False


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update({"point_in_time_decision": True}), "POINT_IN_TIME_DECISION"),
        (
            lambda value: value.update({"decision_eligibility_asserted": True}),
            "AUTHORITY_EVIDENCE_ELIGIBILITY_FORBIDDEN",
        ),
        (
            lambda value: value.update({"governance_fingerprint": "short"}),
            "AUTHORITY_EVIDENCE_GOVERNANCE_FINGERPRINT_INVALID",
        ),
        (
            lambda value: value.update({"governance_fingerprint": "0" * 64}),
            "AUTHORITY_EVIDENCE_GOVERNANCE_FINGERPRINT_MISMATCH",
        ),
        (
            lambda value: value["retained"]["audit_trail"].update({"healed": True}),
            "AUTHORITY_EVIDENCE_HEALING_FORBIDDEN",
        ),
    ],
)
def test_rejects_forbidden_inputs(mutation, error):
    retained = _retained()
    mutation(retained)
    with pytest.raises(Rejected) as exc:
        enforce_authority_evidence_completeness_report_audit_trail(retained)
    assert exc.value.args[0] == error
