"""Native storage + independent JSONL input-to-event derivation; not identity semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.bronze_jsonl_recompute import (
    COMMAND,
    CONFIG_HASH,
    JsonlImportPlan,
    JsonlRecomputeRejected,
    canonical,
    decode_import_plan,
    hash_pin,
    recompute_jsonl,
    sha,
    verify_plan_inputs,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import (
        BronzeSupportEvidence,
        BronzeSupportPin,
    )

VERSION = "bronze-jsonl-support-consumer@1"


@dataclass(frozen=True)
class JsonlDerivationObservation:
    status: str
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str | None = None


@dataclass(frozen=True)
class JsonlSupportEvidence:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    storage_before: BronzeSupportEvidence | None = None
    storage_after: BronzeSupportEvidence | None = None
    derivation_before: JsonlDerivationObservation | None = None
    derivation_after: JsonlDerivationObservation | None = None
    artifact_to_event_semantics_verified: bool = False
    original_plan_binding_verified: bool = False
    evidence_fingerprint: str | None = None
    identity_semantics_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    retry_link_coverage_verified: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def _observe(
    bronze: Any, support: BronzeSupportPin, plan: JsonlImportPlan
) -> JsonlDerivationObservation:
    from nse_quant.data_platform import bronze_support_reader as source
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    bronze.execute("BEGIN TRANSACTION")
    try:
        rows = source._select(
            bronze,
            source._name(bronze, "bronze", "event_variants"),
            source.EVENT_COLUMNS,
            "capture_event_id=? AND envelope_hash=?",
            [support.capture_event_id, support.envelope_hash],
            1,
        )
        if len(rows) != 1:
            raise JsonlRecomputeRejected("JSONL_TARGET_EVENT_MISSING")
        target = rows[0]
        source._verify_event(target)
        batch_key, origin_job = target[14:16]
        batches = source._select(
            bronze,
            source._name(bronze, "bronze", "ingest_batches"),
            (
                "batch_key",
                "input_file_hash",
                "input_events",
                "inserted_variants",
                "exact_retries",
                "conflict_variants",
                "job_id",
            ),
            "batch_key=?",
            [batch_key],
            1,
        )
        if (
            len(batches) != 1
            or any(type(x) is not int for x in batches[0][2:6])
            or batches[0][2:6] != (batches[0][2], batches[0][2], 0, 0)
        ):
            raise JsonlRecomputeRejected("JSONL_FRESH_BATCH_NOT_ESTABLISHED")
        batch = batches[0]
        if batch[6] != origin_job or type(batch[2]) is not int or not 1 <= batch[2] <= 64:
            raise JsonlRecomputeRejected("JSONL_BATCH_ORIGIN_OR_COUNT_MISMATCH")
        artifacts = source._select(
            bronze,
            source._name(bronze, "bronze", "input_artifacts"),
            (
                "artifact_hash",
                "artifact_bytes",
                "recorded_at",
                "first_job_id",
            ),
            "artifact_hash=?",
            [batch[1]],
            1,
        )
        if len(artifacts) != 1 or artifacts[0][3] != origin_job:
            raise JsonlRecomputeRejected("JSONL_INPUT_ARTIFACT_ORIGIN_NOT_SUPPORTED")
        artifact = recompute_jsonl(artifacts[0][1])
        if artifact.artifact_hash != batch[1] or len(artifact.envelopes) != batch[2]:
            raise JsonlRecomputeRejected("JSONL_ARTIFACT_HASH_OR_COUNT_MISMATCH")
        event_table = source._name(bronze, "bronze", "event_variants")
        capacity = bronze.execute(
            f"SELECT count(*),coalesce(sum(octet_length(payload)),0),"
            f"coalesce(max(octet_length(payload)),0) FROM {event_table} WHERE first_batch_key=?",
            [batch_key],
        ).fetchone()
        if (
            capacity[0] != batch[2]
            or capacity[1] > source.MAX_BATCH_BYTES
            or capacity[2] > source.MAX_PAYLOAD_BYTES
        ):
            raise JsonlRecomputeRejected("JSONL_MEMBER_MATERIALIZATION_LIMIT")
        members = source._select(
            bronze,
            event_table,
            source.EVENT_COLUMNS,
            "first_batch_key=?",
            [batch_key],
            64,
            order="ORDER BY ingest_sequence",
        )
        if len(members) != len(artifact.envelopes):
            raise JsonlRecomputeRejected("JSONL_STORED_MEMBERSHIP_COUNT_MISMATCH")
        for member, event in zip(members, artifact.envelopes, strict=True):
            source._verify_event(member)
            if (
                (member[0], member[1], member[10], member[13])
                != (
                    event.capture_event_id,
                    event.envelope_hash,
                    event.payload_hash,
                    event.envelope_json,
                )
                or member[9] != event.payload
                or member[14:16] != (batch_key, origin_job)
            ):
                raise JsonlRecomputeRejected("JSONL_RECOMPUTED_EVENT_OR_ORDER_MISMATCH")
        jobs = source._select(
            bronze,
            source._name(bronze, "medallion_audit", "jobs"),
            (
                "job_id",
                "actor_id",
                "code_revision",
                "command_name",
                "scope_ref",
                "config_hash",
            ),
            "scope_ref=? OR job_id=?",
            ["sha256:" + plan.plan_sha256, origin_job],
            source.MAX_JOBS,
            order="ORDER BY job_id",
        )
        if not jobs or origin_job not in {job[0] for job in jobs}:
            raise JsonlRecomputeRejected("JSONL_ORIGIN_JOB_MISSING")
        for job in jobs:
            if job[3:] != (COMMAND, "sha256:" + plan.plan_sha256, CONFIG_HASH):
                raise JsonlRecomputeRejected("JSONL_IMPORTER_JOB_METADATA_MISMATCH")
            verify_plan_inputs(
                plan, artifact, batch_key=batch_key, actor_id=job[1], code_revision=job[2]
            )
        contract = DatasetContract(
            "bronze.event_variants",
            "1",
            Layer.BRONZE,
            WritePolicy.APPEND_OBSERVATIONS,
            ("capture_event_id", "envelope_hash"),
            (
                "capture_event_id",
                "envelope_hash",
                "received_at",
                "recorded_at",
                "source",
                "payload_hash",
            ),
            "capture",
        )
        contracts = source._name(bronze, "medallion_audit", "dataset_contracts")
        registered = bronze.execute(
            f"SELECT CASE WHEN length(fingerprint)=64 THEN fingerprint END,"
            f"CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END,"
            f"registered_at "
            f"FROM {contracts} WHERE dataset_name=? AND contract_version='1' LIMIT 2",
            [contract.name],
        ).fetchall()
        if len(registered) != 1 or registered[0][:2] != (
            contract.fingerprint,
            contract.canonical_json(),
        ):
            raise JsonlRecomputeRejected("JSONL_NATIVE_BRONZE_CONTRACT_MISMATCH")
        source._instant(registered[0][2])
        fingerprint = sha(
            source._canonical(
                [
                    VERSION,
                    plan.plan_sha256,
                    artifact.artifact_hash,
                    target,
                    batch,
                    members,
                    artifacts,
                    jobs,
                    registered,
                ]
            ).encode()
        )
        result = JsonlDerivationObservation(
            "verified", ("EXACT_JSONL_DERIVATION_RECOMPUTED",), fingerprint
        )
    except (JsonlRecomputeRejected, source.SupportReviewRequired) as error:
        result = JsonlDerivationObservation("review_required", (str(error),))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        result = JsonlDerivationObservation("review_required", ("JSONL_DERIVATION_NOT_VERIFIED",))
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    bronze.execute("COMMIT")
    return result


def inspect_jsonl_bronze_support(
    bronze: Any,
    *,
    support: BronzeSupportPin,
    plan_bytes: bytes,
    expected_plan_sha256: str,
) -> JsonlSupportEvidence:
    """Independent strict source profile; native parser/writer is NEVER executed or altered.

    Caller supplies exact original canonical import-plan bytes and reviewed SHA256.
    Two storage observations bracket two derivation observations; no atomicity claim.
    """
    from nse_quant.data_platform import bronze_support_reader as source

    if source.VERSION != "pinned-bronze-support-storage@1":
        raise ValueError("UNSUPPORTED_JSONL_STORAGE_DEPENDENCY_VERSION")
    plan = decode_import_plan(plan_bytes, expected_plan_sha256=expected_plan_sha256)
    audit = source.IngestAuditExpectation(COMMAND, "sha256:" + plan.plan_sha256, CONFIG_HASH)

    def complete(value: source.BronzeSupportEvidence) -> bool:
        return (
            type(value) is source.BronzeSupportEvidence
            and value.version == source.VERSION
            and value.status == "verified_storage_evidence"
            and value.capture_event_id == support.capture_event_id
            and all(
                flag is True
                for flag in (
                    value.current_payload_integrity_verified,
                    value.retained_input_artifact_verified,
                    value.fresh_batch_membership_verified,
                    value.origin_ingest_audit_verified,
                    value.scoped_audit_history_verified,
                )
            )
            and value.audit_obligation_job_ids == ()
            and hash_pin(value.evidence_fingerprint)
            and all(
                flag is False
                for flag in (
                    value.artifact_to_event_semantics_verified,
                    value.retry_link_coverage_verified,
                    value.identity_verified,
                    value.issuer_authenticated,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.source_acquisition_authenticity_asserted,
                )
            )
        )

    before = source.inspect_bronze_support(bronze, support=support, expected_audit=audit)
    if not complete(before):
        return JsonlSupportEvidence(
            VERSION,
            "review_required",
            ("JSONL_STORAGE_PROFILE_NOT_VERIFIED",),
            storage_before=before,
        )
    first = _observe(bronze, support, plan)
    second = _observe(bronze, support, plan)
    after = source.inspect_bronze_support(bronze, support=support, expected_audit=audit)
    if (
        not complete(after)
        or canonical(asdict(before)) != canonical(asdict(after))
        or first.status != "verified"
        or second.status != "verified"
        or first != second
        or not hash_pin(first.evidence_fingerprint)
    ):
        return JsonlSupportEvidence(
            VERSION,
            "review_required",
            ("JSONL_DERIVATION_OR_STORAGE_REQUIRES_REVIEW_OR_CHANGED",),
            before,
            after,
            first,
            second,
        )
    fingerprint = sha(
        canonical(
            [
                VERSION,
                plan.plan_sha256,
                asdict(before),
                asdict(after),
                asdict(first),
                asdict(second),
            ]
        ).encode()
    )
    return JsonlSupportEvidence(
        VERSION,
        "verified_jsonl_recomputation",
        ("OBSERVED_JSONL_INPUT_EVENT_DERIVATION_VERIFIED",),
        before,
        after,
        first,
        second,
        True,
        True,
        fingerprint,
    )
