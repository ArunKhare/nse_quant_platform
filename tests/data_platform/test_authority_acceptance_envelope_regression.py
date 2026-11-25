"""Regression for returned report envelope and its content fingerprint."""

import hashlib
import json

from nse_quant.data_platform.native_authority_evidence_completeness_report_acceptance import (
    REQUIRED_OBLIGATIONS,
    VERSION,
    accept_authority_evidence_completeness_report,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def test_acceptance_fingerprint_binds_returned_dictionary():
    report = {
        "version": VERSION,
        "evidence_kind": "identity_time",
        "obligations": list(REQUIRED_OBLIGATIONS),
        "healed": False,
        "decision_eligibility_asserted": False,
    }
    result = accept_authority_evidence_completeness_report(
        {
            "version": VERSION,
            "report": report,
            "round_trip_fingerprint": hashlib.sha256(canonical(report)).hexdigest(),
            "point_in_time_decision": False,
            "decision_eligibility_asserted": False,
        }
    )
    accepted = result["accepted"]
    assert type(accepted) is dict
    assert accepted["report"] == report
    assert accepted["complete"] is True
    assert accepted["missing_obligations"] == []
    assert accepted["decision_eligibility_asserted"] is False
    assert result["decision_eligibility_asserted"] is False
    assert result["acceptance_fingerprint"] == hashlib.sha256(canonical(accepted)).hexdigest()
