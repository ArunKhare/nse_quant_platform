"""Silver-backed native strategy input coverage; read-only, no eligibility."""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform import legacy_daily_rv_observations_silver as daily_rv
from nse_quant.data_platform import legacy_market_events_silver_store as market_events
from nse_quant.data_platform import legacy_regime_policy_silver_store as regime_policy
from nse_quant.data_platform import legacy_spot_features_silver as spot_features
from nse_quant.data_platform import legacy_underlying_iv_observations_silver as underlying_iv
from nse_quant.data_platform import native_option_chain_snapshot_silver as option_chain
from nse_quant.data_platform.native_strategy_input_coverage_evidence import (
    EvidencePin,
    Rejected,
    derive_native_strategy_input_coverage,
)

MAPPINGS: tuple[tuple[str, str], ...] = (
    ("iv_rank_and_history", "underlying_iv_observations"),
    ("iv_rv_spread", "daily_rv_observations+underlying_iv_observations"),
    ("expected_move", "spot_features"),
    ("effective_proposal_configuration", "regime_policy"),
    ("market_session", "market_events"),
    ("chain_time_expiry_spot", "option_chain_snapshot"),
    ("option_chain_and_contract_terms", "option_chain_snapshot"),
    ("candidate_liquidity", "option_chain_snapshot"),
)

UNMAPPED: tuple[str, ...] = ("authoritative_identity_and_time",)


def _pin(requirement_id: str, revision_id: str, fingerprint: str, row_count: int) -> EvidencePin:
    return EvidencePin(
        requirement_id=requirement_id,
        revision_id=revision_id,
        recording_fingerprint=fingerprint,
        row_count=row_count,
    )


def observe_silver_coverage(
    *,
    underlying_iv_revision_id: str,
    underlying_iv_fingerprint: str,
    underlying_iv_row_count: int,
    daily_rv_revision_id: str,
    daily_rv_fingerprint: str,
    daily_rv_row_count: int,
    spot_features_revision_id: str,
    spot_features_fingerprint: str,
    spot_features_row_count: int,
    regime_policy_revision_id: str,
    regime_policy_fingerprint: str,
    regime_policy_row_count: int,
    market_events_revision_id: str,
    market_events_fingerprint: str,
    market_events_row_count: int,
    option_chain_revision_id: str,
    option_chain_fingerprint: str,
    option_chain_row_count: int,
) -> dict[str, EvidencePin]:
    """Build evidence pins from caller-supplied reviewed Silver recording metadata."""
    return {
        "iv_rank_and_history": _pin(
            "iv_rank_and_history",
            underlying_iv_revision_id,
            underlying_iv_fingerprint,
            underlying_iv_row_count,
        ),
        "iv_rv_spread": _pin(
            "iv_rv_spread",
            daily_rv_revision_id,
            daily_rv_fingerprint,
            daily_rv_row_count,
        ),
        "expected_move": _pin(
            "expected_move",
            spot_features_revision_id,
            spot_features_fingerprint,
            spot_features_row_count,
        ),
        "effective_proposal_configuration": _pin(
            "effective_proposal_configuration",
            regime_policy_revision_id,
            regime_policy_fingerprint,
            regime_policy_row_count,
        ),
        "market_session": _pin(
            "market_session",
            market_events_revision_id,
            market_events_fingerprint,
            market_events_row_count,
        ),
        "chain_time_expiry_spot": _pin(
            "chain_time_expiry_spot",
            option_chain_revision_id,
            option_chain_fingerprint,
            option_chain_row_count,
        ),
        "option_chain_and_contract_terms": _pin(
            "option_chain_and_contract_terms",
            option_chain_revision_id,
            option_chain_fingerprint,
            option_chain_row_count,
        ),
        "candidate_liquidity": _pin(
            "candidate_liquidity",
            option_chain_revision_id,
            option_chain_fingerprint,
            option_chain_row_count,
        ),
    }


def derive_silver_backed_coverage(evidence: dict[str, EvidencePin]) -> dict[str, Any]:
    """Derive coverage from Silver-backed evidence pins; observational only."""
    if type(evidence) is not dict:
        raise Rejected("EXACT_EVIDENCE_MAPPING_REQUIRED")
    known = frozenset(requirement_id for requirement_id, _source in MAPPINGS)
    unknown = sorted(set(evidence) - known)
    if unknown:
        raise Rejected("UNKNOWN_SILVER_BACKED_REQUIREMENT")
    return derive_native_strategy_input_coverage(evidence)


def read_silver_recording_metadata(
    reader: Any,
    *,
    family: str,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[str, str, int]:
    """Read and verify one Silver recording; returns (revision, fingerprint, row_count)."""
    if family == "underlying_iv_observations":
        records = underlying_iv.read_underlying_iv_observations_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    elif family == "daily_rv_observations":
        records = daily_rv.read_daily_rv_observations_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    elif family == "spot_features":
        records = spot_features.read_spot_features_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    elif family == "regime_policy":
        records = regime_policy.read_regime_policy_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    elif family == "market_events":
        records = market_events.read_market_events_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    elif family == "option_chain_snapshot":
        records = option_chain.read_option_chain_snapshot_silver(
            reader,
            revision_id=revision_id,
            expected_recording_fingerprint=expected_recording_fingerprint,
        )
    else:
        raise Rejected("UNKNOWN_SILVER_FAMILY")
    return revision_id, expected_recording_fingerprint, len(records)
