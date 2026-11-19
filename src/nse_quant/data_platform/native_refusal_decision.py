"""Exact refusal-only native pre-strategy decisions; never proposal/risk/execution approval."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import native_strategy_requirements as requirements

VERSION = "native-iron-condor-prestrategy-refusal@1"
MAX_BYTES = 8388608
DEFINITION = (
    VERSION,
    requirements.VERSION,
    requirements.DEFINITION_SHA256,
    "kill-switch before safety before native publication admission",
    "no positive decision lane; later stages remain NOT_RUN",
    "missing observations are NOT_OBSERVED, never fabricated missing/ready inputs",
    "complete retained refused outcome replay only, not full strategy replay",
)


class NativeDecisionRejected(ValueError):
    """Fixed diagnostic codes; operational exceptions propagate."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise NativeDecisionRejected("DECISION_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise NativeDecisionRejected("DECISION_NONFINITE_JSON")


def parse(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise NativeDecisionRejected("DECISION_BYTE_BOUND")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise NativeDecisionRejected("DECISION_CANONICAL_OBJECT_REQUIRED")
        return value
    except NativeDecisionRejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise NativeDecisionRejected("DECISION_MALFORMED_JSON") from None


def clock(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise NativeDecisionRejected("DECISION_AWARE_REQUEST_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class RefusalRequest:
    attempt_id: str
    publication_id: str
    expected_publication_evidence_fingerprint: str
    knowledge_cutoff: datetime
    economic_at: datetime
    reviewed_code_revision: str
    kill_switch: str = "UNKNOWN"
    live_requested: bool = False
    dry_run: bool = True
    paper_only: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.attempt_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.attempt_id) is None
            or not pin(self.publication_id)
            or not pin(self.expected_publication_evidence_fingerprint)
            or type(self.reviewed_code_revision) is not str
            or re.fullmatch(r"[a-f0-9]{40}", self.reviewed_code_revision) is None
            or type(self.kill_switch) is not str
            or self.kill_switch not in ("ACTIVE", "INACTIVE", "UNKNOWN")
            or any(
                type(x) is not bool for x in (self.live_requested, self.dry_run, self.paper_only)
            )
        ):
            raise NativeDecisionRejected("EXACT_NATIVE_REFUSAL_REQUEST_REQUIRED")
        clock(self.knowledge_cutoff)
        clock(self.economic_at)


def request_document(request: RefusalRequest) -> dict[str, Any]:
    if type(request) is not RefusalRequest:
        raise NativeDecisionRejected("TYPED_NATIVE_REFUSAL_REQUEST_REQUIRED")
    request = RefusalRequest(**asdict(request))
    return dict(
        asdict(request),
        knowledge_cutoff=clock(request.knowledge_cutoff),
        economic_at=clock(request.economic_at),
    )


def _source_sha(path: Path) -> str:
    with path.open("rb") as handle:
        raw = handle.read(1048577)
    if len(raw) > 1048576:
        raise NativeDecisionRejected("DECISION_SOURCE_CONTEXT_BYTE_BOUND")
    return sha(raw)


def runtime_context() -> dict[str, object]:
    """Actual local code/runtime pins, not authenticated build attestation or all dependencies."""
    root = Path(__file__).parent
    names = (
        "native_strategy_requirements.py",
        "native_refusal_decision.py",
        "native_refusal_service.py",
        "native_refusal_store.py",
    )
    return dict(
        profile=VERSION,
        definition_sha256=sha(canonical(DEFINITION)),
        python_version=platform.python_version(),
        implementation=platform.python_implementation(),
        byteorder=sys.byteorder,
        source_sha256={n: _source_sha(root / n) for n in names},
    )


def _early(request: dict[str, Any]) -> tuple[str, tuple[str, ...]] | None:
    if request["kill_switch"] != "INACTIVE":
        return "kill_switch", (
            "KILL_SWITCH_ACTIVE"
            if request["kill_switch"] == "ACTIVE"
            else "KILL_SWITCH_STATE_UNKNOWN",
        )
    if request["live_requested"]:
        return "safety_boundary", ("LIVE_EXECUTION_DISABLED",)
    if not request["dry_run"]:
        return "safety_boundary", ("DRY_RUN_REQUIRED",)
    if not request["paper_only"]:
        return "safety_boundary", ("PAPER_ONLY_BOUNDARY_REQUIRED",)
    return None


def admission_may_be_observed(request: RefusalRequest) -> bool:
    return _early(request_document(request)) is None


def _evaluate(frozen: dict[str, Any]) -> dict[str, object]:
    if set(frozen) != {"version", "request", "runtime", "admission_receipts_hex", "dependencies"}:
        raise NativeDecisionRejected("DECISION_FROZEN_INPUT_SCHEMA")
    if frozen["version"] != VERSION or frozen["runtime"] != runtime_context():
        raise NativeDecisionRejected("DECISION_CODE_OR_RUNTIME_CONTEXT_DRIFT")
    doc = frozen["request"]
    if not isinstance(doc, dict) or set(doc) != set(RefusalRequest.__dataclass_fields__):
        raise NativeDecisionRejected("DECISION_REQUEST_SCHEMA")
    try:
        checked = RefusalRequest(
            **dict(
                doc,
                knowledge_cutoff=datetime.fromisoformat(doc["knowledge_cutoff"]),
                economic_at=datetime.fromisoformat(doc["economic_at"]),
            )
        )
    except (ValueError, TypeError, KeyError, OverflowError):
        raise NativeDecisionRejected("DECISION_REQUEST_MALFORMED") from None
    if request_document(checked) != doc:
        raise NativeDecisionRejected("DECISION_CANONICAL_REQUEST_REQUIRED")
    receipts = frozen["admission_receipts_hex"]
    if (
        not isinstance(receipts, list)
        or len(receipts) not in (0, 2)
        or any(
            type(x) is not str
            or len(x) > MAX_BYTES
            or len(x) % 2
            or re.fullmatch(r"[a-f0-9]+", x) is None
            for x in receipts
        )
    ):
        raise NativeDecisionRejected("DECISION_ADMISSION_OBSERVATION_BOUND")
    early = _early(doc)
    if early is not None:
        if receipts or frozen["dependencies"] != {}:
            raise NativeDecisionRejected("DECISION_EARLY_REFUSAL_MUST_NOT_OBSERVE_ADMISSION")
        failed_stage, reasons = early
        observed = False
    elif not receipts:
        if frozen["dependencies"] != {}:
            raise NativeDecisionRejected("DECISION_UNOBSERVED_DEPENDENCY_CONTEXT")
        failed_stage, reasons = "publication_admission", ("ADMISSION_NOT_OBSERVED",)
        observed = False
    else:
        from nse_quant.data_platform import publication_admission as policy
        from nse_quant.data_platform import quote_publication_reader as reader

        dependencies = _dependency_context(policy, reader)
        if frozen["dependencies"] != dependencies:
            raise NativeDecisionRejected("DECISION_ADMISSION_DEPENDENCY_CONTEXT_DRIFT")
        replayed: list[policy.AdmissionReceipt] = []
        for text in receipts:
            raw = bytes.fromhex(text)
            value = policy.replay_admission_receipt(raw, expected_receipt_id=sha(raw))
            inner = json.loads(value.frozen_input_json)
            if (
                value.policy_version != "research-publication-admission@1"
                or value.publication_id != doc["publication_id"]
                or inner["request"]
                != dict(
                    use_case=policy.POINT_IN_TIME,
                    knowledge_cutoff=doc["knowledge_cutoff"],
                    economic_at=doc["economic_at"],
                )
            ):
                raise NativeDecisionRejected("DECISION_EXACT_ADMISSION_REQUEST_MISMATCH")
            replayed.append(value)
        failed_stage, observed = "publication_admission", True
        if receipts[0] != receipts[1]:
            reasons = ("ADMISSION_FULL_OBSERVATION_DRIFT",)
        elif (
            replayed[0].source_evidence_fingerprint
            != doc["expected_publication_evidence_fingerprint"]
        ):
            reasons = ("REVIEWED_PUBLICATION_EVIDENCE_PIN_MISMATCH",)
        elif replayed[0].status != "REJECTED":
            raise NativeDecisionRejected("NO_SUPPORTED_POSITIVE_NATIVE_DECISION_CONTRACT")
        else:
            reasons = ("POINT_IN_TIME_ADMISSION_REJECTED",) + replayed[0].reason_codes
    stopped = requirements.STAGES.index(failed_stage)
    trace: list[dict[str, str]] = []
    for index, stage in enumerate(requirements.STAGES):
        state = "PASSED" if index < stopped else "BLOCKED" if index == stopped else "NOT_RUN"
        trace.append(dict(stage=stage, status=state))
    return dict(
        status="REFUSED_PRE_STRATEGY",
        failed_stage=failed_stage,
        reason_codes=reasons,
        stage_trace=trace,
        input_requirements_version=requirements.VERSION,
        input_requirements_sha256=requirements.DEFINITION_SHA256,
        input_inventory=[
            dict(input_id=item[0], state="NOT_ADMITTED" if observed else "NOT_OBSERVED")
            for item in requirements.REQUIREMENTS
        ],
        inventory_scope="DIRECT_PROPOSAL_REQUIREMENTS_NOT_COMPLETE_PORTFOLIO_OR_LOOP",
        safety_observation_origin="EXPLICIT_REQUEST_NOT_AUTHENTICATED_LIVE_SWITCH_OBSERVATION",
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


def _dependency_context(policy: Any, reader: Any) -> dict[str, object]:
    from importlib.metadata import version

    if (
        policy.POLICY_VERSION != "research-publication-admission@1"
        or reader.READER_VERSION != "research-quote-publication-consumer@1"
    ):
        raise NativeDecisionRejected("UNSUPPORTED_NATIVE_REFUSAL_DEPENDENCY")
    return dict(
        policy_version=policy.POLICY_VERSION,
        definition_sha256=policy.DEFINITION_FINGERPRINT,
        admission_source_sha256=_source_sha(Path(policy.__file__)),
        publication_reader_sha256=_source_sha(Path(reader.__file__)),
        duckdb_version=version("duckdb"),
    )


def make_refusal_entry(
    request: RefusalRequest,
    *,
    admission_receipts: tuple[bytes, ...] = (),
) -> bytes:
    """Codec only; supplied receipts reverify, no positive gate/claim can be imported."""
    if type(admission_receipts) is not tuple or len(admission_receipts) not in (0, 2):
        raise NativeDecisionRejected("DECISION_EXACT_ADMISSION_OBSERVATIONS_REQUIRED")
    if any(type(x) is not bytes or not 0 < len(x) <= MAX_BYTES // 2 for x in admission_receipts):
        raise NativeDecisionRejected("DECISION_ADMISSION_RECEIPT_BOUND")
    if sum(len(x) for x in admission_receipts) > MAX_BYTES // 2:
        raise NativeDecisionRejected("DECISION_ENTRY_BYTE_BOUND")
    dependencies: dict[str, object] = {}
    if admission_receipts:
        from nse_quant.data_platform import publication_admission as policy
        from nse_quant.data_platform import quote_publication_reader as reader

        dependencies = _dependency_context(policy, reader)
    frozen = dict(
        version=VERSION,
        request=request_document(request),
        runtime=runtime_context(),
        admission_receipts_hex=[x.hex() for x in admission_receipts],
        dependencies=dependencies,
    )
    result = _evaluate(frozen)
    raw = canonical(dict(version=VERSION, frozen_input=frozen, result=result))
    if len(raw) > MAX_BYTES:
        raise NativeDecisionRejected("DECISION_ENTRY_BYTE_BOUND")
    return raw


def replay_refusal_entry(raw: bytes, *, expected_decision_id: str) -> dict[str, Any]:
    """Complete original refusal replay under exact supported code/context. No DB opens.

    Later strategy/risk/execution never ran; their data/results are not invented.
    Content/context consistency is not source authenticity or a historical authority claim.
    """
    value = parse(raw)
    if not pin(expected_decision_id) or sha(raw) != expected_decision_id:
        raise NativeDecisionRejected("DECISION_ENTRY_PIN_MISMATCH")
    if set(value) != {"version", "frozen_input", "result"} or value["version"] != VERSION:
        raise NativeDecisionRejected("DECISION_ENTRY_SCHEMA")
    if not isinstance(value["frozen_input"], dict):
        raise NativeDecisionRejected("DECISION_FROZEN_INPUT_SCHEMA")
    rebuilt = dict(
        version=VERSION, frozen_input=value["frozen_input"], result=_evaluate(value["frozen_input"])
    )
    if canonical(rebuilt) != raw:
        raise NativeDecisionRejected("DECISION_COMPLETE_REPLAY_MISMATCH")
    return value
