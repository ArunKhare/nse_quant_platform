"""Native producer acceptance candidate; no computation-boundary substitutes."""

from contextlib import ExitStack

import duckdb
import pytest
from native_acceptance_case import NativeAcceptanceCase

from nse_quant.data_platform.publication_admission import replay_admission_receipt


@pytest.fixture
def native_case(tmp_path):
    with ExitStack() as stack:
        case = NativeAcceptanceCase(tmp_path, stack)
        yield case, case.run(stack)


def test_received_bytes_to_native_refusal_and_exact_policy_replay(native_case):
    _, result = native_case
    receipt = result["receipt"]
    assert receipt.reason_codes == (
        "RESEARCH_ONLY_PURPOSE_NOT_DECISION_INPUT",
        "AVAILABILITY_EVIDENCE_UNKNOWN",
        "PUBLICATION_RECORD_AND_AUDIT_CLOCKS_ARE_NOT_AVAILABILITY_PROOF",
        "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN",
        "CANONICAL_CONTRACT_IDENTITY_UNKNOWN",
        "DECISION_ELIGIBILITY_NOT_ASSERTED",
    )
    assert (
        replay_admission_receipt(
            result["raw"],
            expected_receipt_id=receipt.receipt_id,
        )
        == receipt
    )
    assert not receipt.research_analysis_permitted
    assert not receipt.availability_evidence_verified
    assert not receipt.economic_validity_verified
    assert not receipt.replay_authenticity_asserted
    assert result["current"].decision_eligibility_asserted is False


def test_wrong_receipt_pin_and_changed_bytes_fail(native_case):
    _, result = native_case
    for raw, pin in (
        (result["raw"], "0" * 64),
        (result["raw"] + b" ", result["receipt"].receipt_id),
    ):
        with pytest.raises(ValueError, match="CHECKSUM"):
            replay_admission_receipt(raw, expected_receipt_id=pin)


def test_source_handles_are_actually_readonly(native_case):
    _, result = native_case
    for conn in (*result["sources"], result["gold"]):
        with pytest.raises(duckdb.InvalidInputException) as caught:
            conn.execute('CREATE TABLE "must_not_write" (id INTEGER)')
        assert "read-only" in str(caught.value).lower()
