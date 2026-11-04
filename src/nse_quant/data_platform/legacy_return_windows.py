"""Policy-explicit fixed-elapsed research windows; not conventional realized volatility."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from fractions import Fraction
from typing import Any

VERSION = "legacy-fixed-elapsed-simple-return-windows@1"
MAX_ROWS = 16000
MAX_ROW_BYTES = 65536
MAX_TOTAL_BYTES = 33554432
MAX_RATIONAL_BITS = 8192


@dataclass(frozen=True)
class ReturnWindowPolicy:
    window_returns: int
    cadence_microseconds: int

    def __post_init__(self) -> None:
        if (
            type(self.window_returns) is not int
            or not 2 <= self.window_returns <= 256
            or type(self.cadence_microseconds) is not int
            or not 1 <= self.cadence_microseconds <= 86400000000
        ):
            raise ValueError("EXPLICIT_BOUNDED_RETURN_WINDOW_POLICY_REQUIRED")


def _bounded(value: Fraction) -> Fraction:
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > MAX_RATIONAL_BITS:
        raise ValueError("RETURN_WINDOW_RATIONAL_RESOURCE_BOUND")
    return value


def _ratio(value: Fraction) -> dict[str, str]:
    _bounded(value)
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def window_statistics(
    fields: tuple[dict[str, Any], ...], *, policy: ReturnWindowPolicy
) -> tuple[dict[str, Any], ...]:
    """Pure complete-set computation; calls accepted adjacent-return kernel.

    Requires N+1 consecutive retained rows, positive closes, stable known symbol and
    exact caller-reviewed elapsed cadence. Never infers sessions or authoritative grids.
    """
    from nse_quant.data_platform.legacy_candle_returns import _close, adjacent_candle_features

    if type(policy) is not ReturnWindowPolicy:
        raise TypeError("TYPED_RETURN_WINDOW_POLICY_REQUIRED")
    policy = ReturnWindowPolicy(**asdict(policy))
    if type(fields) is not tuple or not 1 <= len(fields) <= MAX_ROWS:
        raise ValueError("RETURN_WINDOW_COMPLETE_ROW_BOUND")
    adjacent = adjacent_candle_features(fields)
    groups: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)
    for ordinal, row in enumerate(fields):
        groups[(row["instrument_token"], row["interval"])].append(
            (datetime.fromisoformat(row["ts"]), ordinal)
        )
    results: dict[int, dict[str, Any]] = {}
    for (_token, interval), members in groups.items():
        members.sort()
        for index, (_at, ordinal) in enumerate(members):
            selected = members[max(0, index - policy.window_returns) : index + 1]
            ordinals = [o for _t, o in selected]
            reasons: list[str] = []
            if len(selected) != policy.window_returns + 1:
                reasons.append("INSUFFICIENT_RETAINED_OBSERVATIONS")
            if not interval:
                reasons.append("INTERVAL_LABEL_UNKNOWN")
            symbols = {fields[o]["symbol"] for o in ordinals}
            if len(symbols) != 1 or None in symbols or "" in symbols:
                reasons.append("SYMBOL_UNKNOWN_OR_CHANGED")
            prices = [_close(fields[o]["close"]) for o in ordinals]
            if any(p is None for p in prices):
                reasons.append("MISSING_CLOSE_IN_WINDOW")
            if any(p is not None and p <= 0 for p in prices):
                reasons.append("NONPOSITIVE_CLOSE_IN_WINDOW")
            for (_before, a), (_after, b) in zip(selected, selected[1:], strict=False):
                if adjacent[b]["predecessor_ordinal"] != a:
                    raise ValueError("RETURN_WINDOW_PREDECESSOR_CONTENT_MISMATCH")
                if adjacent[b]["elapsed_stored_microseconds"] != str(policy.cadence_microseconds):
                    reasons.append("ELAPSED_CADENCE_MISMATCH")
            cadence_matched = len(selected) == policy.window_returns + 1 and all(
                adjacent[o]["elapsed_stored_microseconds"] == str(policy.cadence_microseconds)
                for o in ordinals[1:]
            )
            total = mean = None
            if not reasons:
                value = Fraction(0)
                for o in ordinals[1:]:
                    ratio = adjacent[o]["simple_return"]
                    if ratio is None:
                        raise ValueError("RETURN_WINDOW_COMPLETE_OPERAND_MISSING")
                    r = Fraction(int(ratio["numerator"]), int(ratio["denominator"]))
                    value = _bounded(value + _bounded(r * r))
                total, mean = _ratio(value), _ratio(_bounded(value / policy.window_returns))
            results[ordinal] = dict(
                status="COMPUTED_RESEARCH_WINDOW" if not reasons else "UNAVAILABLE",
                reason_codes=list(dict.fromkeys(reasons)),
                member_ordinals=ordinals,
                window_return_count=policy.window_returns,
                observed_close_count=len(selected),
                expected_elapsed_microseconds=str(
                    policy.window_returns * policy.cadence_microseconds
                ),
                sum_squared_simple_returns=total,
                mean_squared_simple_returns=mean,
                policy_cadence_matched=cadence_matched,
                policy_window_satisfied=not reasons,
                authoritative_market_coverage_verified=False,
            )
    return tuple(results[i] for i in range(len(fields)))


def derive_window_records(
    inputs: tuple[bytes, ...],
    return_rows: tuple[bytes, ...],
    *,
    source_build_id: str,
    source_recording_fingerprint: str,
    policy: ReturnWindowPolicy,
) -> tuple[bytes, ...]:
    """Content-only projection. Native producer must validate the original return recording."""
    import json

    from nse_quant.data_platform import legacy_candle_returns as returns
    from nse_quant.data_platform import legacy_market_gold as gold

    if not gold.pin(source_build_id) or not gold.pin(source_recording_fingerprint):
        raise ValueError("EXACT_RETURN_WINDOW_SOURCE_PINS_REQUIRED")
    docs = gold.validate_source_records(inputs)
    if any(d["source_table"] != "spot_candles" for d in docs):
        raise ValueError("COMPLETE_WINDOW_CANDLE_SOURCE_REQUIRED")
    if type(return_rows) is not tuple or len(return_rows) != len(inputs):
        raise ValueError("COMPLETE_WINDOW_RETURN_COVERAGE_REQUIRED")
    if (
        any(type(r) is not bytes or not 0 < len(r) <= returns.MAX_ROW_BYTES for r in return_rows)
        or sum(map(len, return_rows)) > returns.MAX_TOTAL_BYTES
    ):
        raise ValueError("RETURN_WINDOW_SOURCE_BYTE_BOUND")
    original = json.loads(return_rows[0])
    expected = returns.derive_return_records(
        inputs,
        source_build_id=original["source_build_id"],
        source_recording_fingerprint=original["source_recording_fingerprint"],
    )
    if expected != return_rows:
        raise ValueError("RETURN_WINDOW_FULL_RETURN_CONTENT_MISMATCH")
    statistics = window_statistics(tuple(d["stored_fields"] for d in docs), policy=policy)
    output: list[bytes] = []
    total = 0
    for ordinal, (row, value) in enumerate(zip(return_rows, statistics, strict=True)):
        membership = [(o, gold.sha(return_rows[o])) for o in value["member_ordinals"]]
        raw = gold.canonical(
            dict(
                version=VERSION,
                policy=asdict(policy),
                source_build_id=source_build_id,
                source_recording_fingerprint=source_recording_fingerprint,
                source_ordinal=ordinal,
                source_return_record_id=gold.sha(row),
                window_membership_sha256=gold.sha(gold.canonical(membership)),
                source_observation_id=docs[ordinal]["source_observation_id"],
                partition_index=docs[ordinal]["partition_index"],
                event_ts=docs[ordinal]["stored_fields"]["ts"],
                values=value,
                semantics="FIXED_ELAPSED_RETAINED_SIMPLE_RETURN_SQUARES_NOT_ANNUALIZED_RV",
                canonical_contract_id=None,
                independent_availability_verified=False,
                economic_validity_verified=False,
                published_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        total += len(raw)
        if len(raw) > MAX_ROW_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError("RETURN_WINDOW_OUTPUT_BYTE_BOUND")
        output.append(raw)
    return tuple(output)
