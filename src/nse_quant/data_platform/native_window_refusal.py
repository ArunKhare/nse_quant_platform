"""Window-publication pre-strategy refusals; no supported positive decision lane."""

from __future__ import annotations

import json
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from nse_quant.data_platform import native_refusal_decision as common
from nse_quant.data_platform import native_strategy_requirements as requirements

VERSION = "native-window-prestrategy-refusal@1"
MAX_BYTES = 262144
MAX_RECEIPT_BYTES = 32768
RefusalRequest = common.RefusalRequest
DEFINITION = (
    VERSION,
    requirements.VERSION,
    requirements.DEFINITION_SHA256,
    "reuse native request/safety ordering; consume window admission, never quote admission",
    "expected_publication_evidence_fingerprint means exact window publication recording pin",
    "kill switch then safety then two actual complete point-in-time admission observations",
    "always refusal before native inputs/strategy/portfolio risk/execution; no positive lane",
    "exact original refusal replay, not authenticated source/time/authority or full loop replay",
    MAX_BYTES,
    MAX_RECEIPT_BYTES,
)
canonical = common.canonical
sha = common.sha
pin = common.pin
Rejected = common.NativeDecisionRejected


def runtime_context() -> dict[str, object]:
    """Local exact code/runtime observations, not authenticated build/source attestation."""
    root = Path(__file__).parent
    names = (
        "native_window_refusal.py",
        "native_window_refusal_service.py",
        "native_window_refusal_store.py",
    )
    return dict(
        profile=VERSION,
        definition_sha256=sha(canonical(DEFINITION)),
        native_context=common.runtime_context(),
        source_sha256={n: common._source_sha(root / n) for n in names},
    )


def request_from_document(doc: object) -> common.RefusalRequest:
    if type(doc) is not dict or set(doc) != set(RefusalRequest.__dataclass_fields__):
        raise Rejected("WINDOW_REFUSAL_REQUEST_SCHEMA")
    try:
        request = RefusalRequest(
            **dict(
                doc,
                knowledge_cutoff=datetime.fromisoformat(doc["knowledge_cutoff"]),
                economic_at=datetime.fromisoformat(doc["economic_at"]),
            )
        )
    except (ValueError, TypeError, KeyError, OverflowError):
        raise Rejected("WINDOW_REFUSAL_REQUEST_MALFORMED") from None
    if common.request_document(request) != doc:
        raise Rejected("WINDOW_REFUSAL_CANONICAL_REQUEST_REQUIRED")
    return request


def _dependencies() -> dict[str, object]:
    from nse_quant.data_platform import legacy_window_admission as policy

    publication = policy.publication
    if (
        policy.VERSION != "legacy-window-research-admission@1"
        or publication.VERSION != "legacy-window-research-publication@1"
    ):
        raise Rejected("WINDOW_REFUSAL_UNSUPPORTED_ADMISSION_DEPENDENCY")
    return dict(
        policy_version=policy.VERSION,
        policy_definition_sha256=sha(canonical(policy.DEFINITION)),
        publication_definition_sha256=sha(publication._definition()),
        policy_source_sha256=common._source_sha(Path(policy.__file__)),
        publication_source_sha256=common._source_sha(Path(publication.__file__)),
        bundle_source_sha256=common._source_sha(Path(publication.bundle.__file__)),
        duckdb_version=version("duckdb"),
    )


def _evaluate(frozen: dict[str, Any]) -> dict[str, object]:
    if set(frozen) != {"version", "request", "runtime", "admission_receipts_hex", "dependencies"}:
        raise Rejected("WINDOW_REFUSAL_FROZEN_SCHEMA")
    if frozen["version"] != VERSION or frozen["runtime"] != runtime_context():
        raise Rejected("WINDOW_REFUSAL_CODE_OR_RUNTIME_DRIFT")
    request = request_from_document(frozen["request"])
    doc = common.request_document(request)
    receipts = frozen["admission_receipts_hex"]
    if (
        type(receipts) is not list
        or len(receipts) not in (0, 2)
        or any(
            type(x) is not str
            or not 0 < len(x) <= 2 * MAX_RECEIPT_BYTES
            or len(x) % 2
            or any(c not in "0123456789abcdef" for c in x)
            for x in receipts
        )
    ):
        raise Rejected("WINDOW_REFUSAL_RECEIPT_COMPONENT_BOUND")
    early = common._early(doc)
    observed = False
    if early is not None:
        if receipts or frozen["dependencies"] != {}:
            raise Rejected("WINDOW_REFUSAL_EARLY_GATE_MUST_NOT_OBSERVE_SOURCE")
        failed_stage, reasons = early
    elif not receipts:
        if frozen["dependencies"] != {}:
            raise Rejected("WINDOW_REFUSAL_UNOBSERVED_DEPENDENCY_CONTEXT")
        failed_stage, reasons = "publication_admission", ("WINDOW_ADMISSION_NOT_OBSERVED",)
    else:
        from nse_quant.data_platform import legacy_window_admission as policy

        if frozen["dependencies"] != _dependencies():
            raise Rejected("WINDOW_REFUSAL_ADMISSION_DEPENDENCY_DRIFT")
        values = []
        for text in receipts:
            raw = bytes.fromhex(text)
            receipt = policy.replay_window_admission(raw, expected_receipt_id=sha(raw))
            inner = json.loads(receipt.frozen_input_json)
            if (
                receipt.policy_version != "legacy-window-research-admission@1"
                or inner["source"]["publication_id"] != doc["publication_id"]
                or inner["request"]
                != dict(
                    use_case="POINT_IN_TIME_DECISION",
                    knowledge_cutoff=doc["knowledge_cutoff"],
                    economic_at=doc["economic_at"],
                )
            ):
                raise Rejected("WINDOW_REFUSAL_EXACT_ADMISSION_REQUEST_MISMATCH")
            values.append((receipt, inner))
        observed, failed_stage = True, "publication_admission"
        if receipts[0] != receipts[1]:
            reasons = ("WINDOW_ADMISSION_FULL_OBSERVATION_DRIFT",)
        elif (
            values[0][1]["source"]["recording_fingerprint"]
            != (doc["expected_publication_evidence_fingerprint"])
        ):
            reasons = ("REVIEWED_WINDOW_PUBLICATION_RECORDING_PIN_MISMATCH",)
        elif (
            values[0][0].policy_status != "REJECTED"
            or values[0][0].decision_eligibility_asserted is not False
            or values[0][0].research_analysis_permitted is not False
        ):
            raise Rejected("NO_SUPPORTED_POSITIVE_WINDOW_DECISION_CONTRACT")
        else:
            reasons = ("WINDOW_POINT_IN_TIME_ADMISSION_REJECTED",) + values[0][0].reason_codes
    stopped = requirements.STAGES.index(failed_stage)
    trace = [
        dict(stage=s, status="PASSED" if i < stopped else "BLOCKED" if i == stopped else "NOT_RUN")
        for i, s in enumerate(requirements.STAGES)
    ]
    return dict(
        status="REFUSED_PRE_STRATEGY",
        failed_stage=failed_stage,
        reason_codes=reasons,
        stage_trace=trace,
        input_requirements_version=requirements.VERSION,
        input_requirements_sha256=requirements.DEFINITION_SHA256,
        input_inventory=[
            dict(input_id=r[0], state="NOT_ADMITTED" if observed else "NOT_OBSERVED")
            for r in requirements.REQUIREMENTS
        ],
        inventory_scope="DIRECT_PROPOSAL_REQUIREMENTS_NOT_COMPLETE_PORTFOLIO_OR_LOOP",
        safety_observation_origin="EXPLICIT_REQUEST_NOT_AUTHENTICATED_LIVE_SWITCH_OBSERVATION",
        publication_profile="legacy-window-research-publication@1",
        admission_observed=observed,
        strategy_evaluated=False,
        portfolio_risk_evaluated=False,
        execution_attempted=False,
        order_emitted=False,
        decision_eligibility_asserted=False,
        source_authenticity_asserted=False,
        complete_strategy_replay_asserted=False,
        complete_original_prestrategy_refusal_replay_supported=True,
    )


def make_window_refusal_entry(
    request: common.RefusalRequest, *, admission_receipts: tuple[bytes, ...] = ()
) -> bytes:
    """Codec only. Native producer must observe actual window admission itself."""
    if (
        type(admission_receipts) is not tuple
        or len(admission_receipts) not in (0, 2)
        or any(
            type(r) is not bytes or not 0 < len(r) <= MAX_RECEIPT_BYTES for r in admission_receipts
        )
    ):
        raise Rejected("WINDOW_REFUSAL_EXACT_BOUNDED_ADMISSION_OBSERVATIONS_REQUIRED")
    doc = common.request_document(request)
    if common._early(doc) is not None and admission_receipts:
        raise Rejected("WINDOW_REFUSAL_EARLY_GATE_MUST_NOT_OBSERVE_SOURCE")
    frozen = dict(
        version=VERSION,
        request=doc,
        runtime=runtime_context(),
        admission_receipts_hex=[r.hex() for r in admission_receipts],
        dependencies=_dependencies() if admission_receipts else {},
    )
    raw = canonical(dict(version=VERSION, frozen_input=frozen, result=_evaluate(frozen)))
    if len(raw) > MAX_BYTES:
        raise Rejected("WINDOW_REFUSAL_ENTRY_BYTE_BOUND")
    return raw


def replay_window_refusal_entry(raw: bytes, *, expected_decision_id: str) -> dict[str, Any]:
    """Exact original refusal stages only. No source/current checks or later-stage replay."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise Rejected("WINDOW_REFUSAL_ENTRY_BYTE_BOUND")
    if not pin(expected_decision_id) or sha(raw) != expected_decision_id:
        raise Rejected("WINDOW_REFUSAL_ENTRY_PIN_MISMATCH")
    value = common.parse(raw)
    if (
        set(value) != {"version", "frozen_input", "result"}
        or value["version"] != VERSION
        or type(value["frozen_input"]) is not dict
    ):
        raise Rejected("WINDOW_REFUSAL_ENTRY_SCHEMA")
    rebuilt = dict(
        version=VERSION, frozen_input=value["frozen_input"], result=_evaluate(value["frozen_input"])
    )
    if canonical(rebuilt) != raw:
        raise Rejected("WINDOW_REFUSAL_COMPLETE_REPLAY_MISMATCH")
    return value
