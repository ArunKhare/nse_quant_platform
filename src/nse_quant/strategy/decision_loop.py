"""Paper decision loop: market data to post-trade review.


Flow:
market data -> analytics -> feature snapshot -> open-position monitoring
-> strategy proposal -> gates -> risk check -> paper order
-> independent leg positions -> marking/P&L -> exit evaluation
-> close -> post-trade review.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from nse_quant.analytics.features import build_features
from nse_quant.core.constants import IST
from nse_quant.core.evidence import EvidenceMode
from nse_quant.core.market_calendar import NSE_HOLIDAYS
from nse_quant.core.models import (
    ChainSnapshot,
    GateResult,
    LegPosition,
    MarketFeatures,
    OptionQuote,
    OrderSide,
    PaperOrder,
    PostTradeReview,
    StrategyPosition,
    StrategyPositionStatus,
    TradeProposal,
)
from nse_quant.core.regime_registry import REGIME_REGISTRY_VERSION, is_canonical_regime_label
from nse_quant.core.settings import IronCondorProfileSettings, Settings, get_settings
from nse_quant.core.trading_calendar import NSETradingCalendar
from nse_quant.execution.broker import PaperBroker
from nse_quant.features.availability import FeatureAvailability
from nse_quant.features.availability_checker import (
    FeatureAvailabilityChecker,
)
from nse_quant.features.feature_gates import SpotFeatureGate
from nse_quant.features.feature_service import SpotFeatureService
from nse_quant.features.feature_store import FeatureStore
from nse_quant.ops.data_quality import DataQualityChecker, DataQualityReport
from nse_quant.ops.eligibility_alerts import EligibilityAlertManager
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.live_snapshot import build_snapshot, write_live_snapshot
from nse_quant.ops.notifier import Notifier
from nse_quant.persistence.repositories import (
    DecisionRepository,
    PositionRepository,
)
from nse_quant.research.evidence_plugins.base import DecisionContext, EvidencePlugin
from nse_quant.research.evidence_plugins.event_impact import EventImpactMapper
from nse_quant.research.evidence_plugins.event_risk import EventRiskPlugin
from nse_quant.research.evidence_plugins.execution_quality import ExecutionQualityPlugin
from nse_quant.research.evidence_plugins.institutional_regime import InstitutionalRegimePlugin
from nse_quant.research.evidence_plugins.market_context import MarketContextPlugin
from nse_quant.research.evidence_plugins.market_structure import MarketStructurePlugin
from nse_quant.research.evidence_plugins.mutli_timeframe import MultiTimeframeTrendPlugin
from nse_quant.research.evidence_plugins.option_positioning import OptionPositioningPlugin
from nse_quant.research.evidence_plugins.registry import EvidencePluginRunner
from nse_quant.research.evidence_plugins.technical_indicators import TechnicalIndicatorsPlugin
from nse_quant.research.evidence_plugins.volume_flow import VolumeFlowPlugin
from nse_quant.research.har_realized_volatility import (
    CALIBRATION_MINIMUM_SAMPLES,
    HAR_RV_CALIBRATION_VERSION,
    build_daily_rv_observations,
    calibrate_har_rv_forecast_errors,
    forecast_har_rv_30d,
)
from nse_quant.research.regime_policy import RegimePolicy
from nse_quant.research.regime_policy_evaluation import resolve_effective_regimes
from nse_quant.research.regime_risk_policy import RegimeRiskLimits, build_regime_risk_limits
from nse_quant.research.variance_risk_premium import (
    HAR_RV_HORIZON_DAYS,
    HAR_RV_MEASURE,
    HAR_RV_METHOD,
    HAR_RV_VERSION,
    VRP_CALCULATION_VERSION,
    evaluate_variance_risk_premium,
    trailing_daily_realized_volatility,
)
from nse_quant.risk.risk_engine import RiskEngine
from nse_quant.strategy.canonical_risk_context import (
    canonical_regime_for_risk,
    canonical_risk_rejection,
)
from nse_quant.strategy.exit_engine import ExitEngine
from nse_quant.strategy.iron_condor import IronCondorMonitor
from nse_quant.strategy.timing_filters import MultiTimeframeTimingFilter

logger = logging.getLogger(__name__)


class DecisionLoop:
    def __init__(
        self,
        store: Any,
        provider: Any,
        broker: PaperBroker,
        run_id: str,
        settings: Settings,
        spot_instrument_token_resolver: Callable[[str], int] | None = None,
        feature_gate: SpotFeatureGate | None = None,
        live_snapshot_path: Path | None = None,
        kill_switch: KillSwitch | None = None,
        chain_snapshot_provider: Any | None = None,
    ) -> None:
        self.settings = settings if settings is not None else get_settings()
        self.store = store

        plugins: list[EvidencePlugin] = []

        if self.settings.evidence.enabled:
            mtf = self.settings.evidence.plugins.multi_timeframe

            if mtf.enabled:
                plugins.append(
                    MultiTimeframeTrendPlugin(
                        store=store,
                        timeframes=mtf.timeframes,
                        history_limit=mtf.history_limit,
                    )
                )
        if self.settings.evidence.plugins.event_risk.enabled:
            plugins.append(
                EventRiskPlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.event_risk,
                )
            )

        if self.settings.evidence.plugins.technical_indicators.enabled:
            plugins.append(
                TechnicalIndicatorsPlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.technical_indicators,
                )
            )

        if self.settings.evidence.plugins.volume_flow.enabled:
            plugins.append(
                VolumeFlowPlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.volume_flow,
                )
            )

        if self.settings.evidence.plugins.option_positioning.enabled:
            plugins.append(
                OptionPositioningPlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.option_positioning,
                )
            )

        if self.settings.evidence.plugins.market_structure.enabled:
            plugins.append(
                MarketStructurePlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.market_structure,
                )
            )

        if self.settings.evidence.enabled and self.settings.evidence.plugins.market_context.enabled:
            plugins.append(
                MarketContextPlugin(
                    store=store,
                    settings=self.settings.evidence.plugins.market_context,
                )
            )

        execution_quality = self.settings.evidence.plugins.execution_quality
        if self.settings.evidence.enabled and execution_quality.enabled:
            plugins.append(
                ExecutionQualityPlugin(
                    settings=execution_quality,
                )
            )

        institutional_regime = self.settings.evidence.plugins.institutional_regime
        if self.settings.evidence.enabled and institutional_regime.enabled:
            plugins.append(
                InstitutionalRegimePlugin(
                    store=store,
                    settings=institutional_regime,
                )
            )

        if self.settings.evidence.enabled and self.settings.evidence.plugins.event_impact.enabled:
            plugins.append(
                EventImpactMapper(
                    store=store,
                    settings=self.settings.evidence.plugins.event_impact,
                )
            )

        self.evidence_runner = EvidencePluginRunner(plugins)
        self.provider = provider
        self.broker = broker
        self.run_id = run_id
        self._current_strategy_eligibility: dict[str, Any] | None = None
        self.feature_store = FeatureStore(store.conn)
        self.decisions = DecisionRepository(store.conn)
        self.positions = PositionRepository(store.conn)
        self.risk = RiskEngine(
            store.conn,
            self.settings,
            self.positions,
            risk_settings=self.settings.risk,
        )
        self.exit_engine = ExitEngine(self.settings.get_effective_exit_settings("iron_condor_monitor"))
        self.strategy = IronCondorMonitor(self.settings)
        self.quality_checker = DataQualityChecker(
            stale_seconds=self.settings.runtime.stale_seconds,
        )
        self.feature_service = SpotFeatureService(
            store=store,
            max_age_seconds=int(self.settings.runtime.stale_seconds),
        )
        self.feature_gate = feature_gate or SpotFeatureGate(
            max_age_seconds=int(self.settings.runtime.stale_seconds),
        )
        self._spot_instrument_token_resolver = spot_instrument_token_resolver or self._default_spot_token_resolver
        self.availability_checker = FeatureAvailabilityChecker(store)
        self._live_snapshot_path = live_snapshot_path
        self.eligibility_alerts = EligibilityAlertManager(self.decisions)
        self.kill_switch = kill_switch or KillSwitch()
        # Chain-snapshot source. When an explicit chain_snapshot_provider is
        # supplied (e.g. PersistedChainSnapshotProvider fed by the paper loop's
        # background capture thread), snapshots are already persisted and are
        # not re-written. Otherwise the injected provider is used directly and
        # its snapshot is persisted to option_stream, as before 28b93f3.
        # self.provider is never replaced, so spot-token resolution and other
        # provider capabilities are preserved.
        self.chain_snapshot_provider = chain_snapshot_provider
        self._persist_fetched_snapshots = chain_snapshot_provider is None
        # HAR-RV is based only on completed prior sessions; cache it for the
        # trading date so the 15-second decision loop does not refit it each cycle.
        self._har_rv_cache: dict[
            tuple[int, date],
            tuple[float | None, dict[str, Any], dict[str, Any]],
        ] = {}

    def run_once(self) -> dict[str, Any]:
        self._current_strategy_eligibility = None
        if self.kill_switch.is_active():
            return self.handle_kill_switch()
        symbol = self.settings.market_data.default_symbol
        spot_feature_snapshot = self.feature_service.latest(symbol)
        provider_token = self._resolve_spot_instrument_token(symbol)
        availability = self.availability_checker.evaluate(
            symbol=symbol,
            instrument_token=provider_token,
            as_of=datetime.now(UTC),
        )

        regime_policy: dict[str, Any] | None = None
        total_stale_marks = 0
        persisted_rows = 0

        self.store.write_feature_availability_result(
            gate_result_id=uuid4().hex,
            ts=datetime.now(UTC),
            run_id=self.run_id,
            symbol=symbol,
            passed=availability.core_status == FeatureAvailability.READY,
            reasons=availability.reasons,
            checks={
                "core_status": availability.core_status.value,
                "htf_status": availability.htf_status.value,
                "iv_status": availability.iv_status.value,
                "overall_status": availability.overall_status.value,
                "observations": availability.observations,
                "missing": availability.missing,
                "enforced": (self.settings.research.enforce_feature_availability),
            },
        )

        availability_enforced = self.settings.research.enforce_feature_availability

        if availability_enforced and availability.core_status != FeatureAvailability.READY:
            return {
                "status": "feature_availability_rejected",
                "symbol": symbol,
                "reasons": availability.reasons,
                "checks": {
                    "core_status": availability.core_status.value,
                    "htf_status": availability.htf_status.value,
                    "iv_status": availability.iv_status.value,
                    "overall_status": (availability.overall_status.value),
                },
            }

        if availability_enforced and not availability.can_evaluate_new_entries:
            open_positions = self.positions.get_open_strategy_positions()

            if not open_positions:
                return {
                    "status": "warming_up",
                    "symbol": symbol,
                    "reasons": availability.reasons,
                    "checks": {
                        "overall_status": (availability.overall_status.value),
                        "observations": availability.observations,
                    },
                }

            # Continue only through open-position monitoring/exits.
            return self._monitor_and_exit_only(
                symbol=symbol,
                availability=availability,
                instrument_token=provider_token,
            )
        gate = self.feature_gate.evaluate(spot_feature_snapshot)

        self.store.write_feature_gate_result(
            gate_result_id=uuid4().hex,
            ts=datetime.now(UTC),
            run_id=self.run_id,
            symbol=symbol,
            passed=gate.passed,
            reasons=gate.reasons,
            checks=gate.checks,
        )

        if not gate.passed:
            return {
                "status": "feature_gate_rejected",
                "symbol": symbol,
                "reasons": gate.reasons,
                "checks": gate.checks,
                "evidence": {},
            }

        t0 = time.perf_counter()
        snapshots = self._fetch_chain_snapshots()
        logger.info("chain_snapshots_seconds=%.3f", time.perf_counter() - t0)

        if not snapshots:
            return {
                "status": "no_complete_chain_snapshot",
                "symbol": symbol,
                "reasons": ["No complete option-chain snapshots available"],
                "checks": [],
                "evidence": {},
            }

        snapshot = snapshots[0]
        persisted_rows = self._persist_snapshot(snapshot)

        expiry_count = len({quote.instrument.expiry for quote in snapshot.quotes})

        if expiry_count < self.settings.analytics.expiries_per_snapshot:
            return {
                "status": "incomplete_chain_snapshot",
                "symbol": symbol,
                "reasons": [f"Required {self.settings.analytics.expiries_per_snapshot} expiries; found {expiry_count}"],
                "checks": [],
                "evidence": {},
            }

        t0 = time.perf_counter()
        features, iv_history_count, evidence = self._build_features(snapshot, instrument_token=provider_token)
        timing_filter_result = evidence.get("timing_filter")

        if timing_filter_result is None:
            timing_filter_result = {
                "strategy_id": "unknown",
                "filter_name": "multi_timeframe_timing",
                "filter_version": "multi_timeframe_timing_v1",
                "mode": "observation",
                "status": "OBSERVE",
                "alignment": None,
                "size_multiplier": 1.0,
                "reasons": ["timing_filter_result_missing"],
                "details": {},
            }

            evidence["timing_filter"] = timing_filter_result

        logger.info("features_evidence_seconds=%.3f", time.perf_counter() - t0)

        # Diagnostics
        features.diagnostics["expected_move_inputs"] = self.build_expected_move_diagnostics(
            snapshot=snapshot,
            features=features,
        )

        quality: DataQualityReport = self.quality_checker.assess(snapshot)
        position_outcomes, monitored_stale_marks = self._monitor_open_positions(
            snapshot=snapshot,
            features=features,
            quality=quality,
        )
        total_stale_marks += monitored_stale_marks

        self.feature_store.save(self.run_id, features)

        data_quality = {
            "is_usable": quality.is_usable,
            "stale": quality.stale,
            "missing_quotes": quality.missing_quotes,
            "missing_bid_ask": quality.missing_bid_ask,
            "zero_volume_legs": quality.zero_volume_legs,
            "issues": quality.issues,
            "warnings": quality.warnings,
        }

        self.decisions.save_decision(
            self.run_id,
            "data_quality",
            None,
            data_quality,
        )

        features.diagnostics["iv_smile"] = [
            {
                "strike": quote.instrument.strike,
                "option_type": quote.instrument.option_type.value,
                "iv": quote.iv,
            }
            for quote in snapshot.quotes
            if quote.iv is not None
        ]

        iv_history = {
            "observation_count": iv_history_count,
            "minimum_required": (self.settings.analytics.min_iv_history_observations),
            "mode": (
                "ENFORCED" if iv_history_count >= self.settings.analytics.min_iv_history_observations else "COLD_START"
            ),
        }

        profile = cast(
            IronCondorProfileSettings,
            self.settings.get_strategy_profile("iron_condor_monitor"),
        )
        open_positions = self.positions.get_open_strategy_positions()
        effective_risk = self.settings.get_effective_risk_settings("iron_condor_monitor")
        if len(open_positions) >= effective_risk.max_open_positions:
            return self._finish_cycle(
                status="max_open_positions",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                extra={
                    "open_positions": len(open_positions),
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                },
            )

        timing_mode = EvidenceMode(timing_filter_result["mode"])
        timing_status = timing_filter_result["status"]
        _timing_size_multiplier = float(timing_filter_result["size_multiplier"])
        if timing_mode is EvidenceMode.HARD_GATE and timing_status == "BLOCK":
            return self._finish_cycle(
                status="timing_filter_rejected",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                extra={
                    "timing_filter": timing_filter_result,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                },
            )
        # Mandatory iron-condor VRP entry gate (charter section 7). Fails closed:
        # an unavailable VRP blocks a new entry exactly like a negative one.
        vrp_result = evidence.get("variance_risk_premium") or {}
        if vrp_result.get("applicable") and not vrp_result.get("gate_passed"):
            return self._finish_cycle(
                status="vrp_gate_rejected",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                extra={
                    "rejection_reason": (
                        "variance_risk_premium_unavailable"
                        if not vrp_result.get("available")
                        else (
                            "variance_risk_premium_estimator_not_gate_eligible"
                            if not vrp_result.get("estimator_gate_eligible")
                            else (
                                "variance_risk_premium_iv_not_gate_eligible"
                                if not vrp_result.get("implied_volatility_gate_eligible")
                                else "variance_risk_premium_below_minimum"
                            )
                        )
                    ),
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                },
            )

        if self.settings.research.enforce_strategy_eligibility:
            market_regime = self.store.get_market_regime_as_of(
                symbol=symbol,
                ts=features.ts,
            )
            trend_regime = market_regime.get("trend_regime") if market_regime else None
            volatility_regime = market_regime.get("volatility_regime") if market_regime else None
            market_context_daily_trend_vol = (
                f"{trend_regime}|{volatility_regime}"
                if trend_regime and volatility_regime
                else None
            )
            market_context_source = (
                "daily_market_regime" if market_context_daily_trend_vol else "unavailable"
            )
            market_context_vocabulary = market_regime.get("regime_vocabulary") if market_regime else None

            regime_policy = self.store.latest_regime_policy(
                symbol=symbol,
                as_of=features.ts,
            )

            strategy_id = "iron_condor_monitor"
            profile = self.settings.get_strategy_profile(strategy_id)

            if not isinstance(profile, IronCondorProfileSettings):
                raise TypeError(f"{strategy_id!r} must use IronCondorProfileSettings")

            effective_regimes, _regime_source, _policy_status = resolve_effective_regimes(
                profile,
                learned_policy=regime_policy,
            )

            # Charter section 6: iron-condor eligibility uses the full canonical
            # institutional regime_label. Daily/spot regimes (e.g. BULL|NORMAL)
            # are market context only and are never compared to the allowlist.
            institutional = self._institutional_regime_audit(evidence)
            eligibility_regime = institutional["regime_label"] if institutional["regime_label_eligible"] else None
            regime_allowed = eligibility_regime is not None and eligibility_regime in effective_regimes

            eligibility = self._evaluate_strategy_eligibility(
                profile=profile,
                features=features,
                iv_history_count=iv_history_count,
                regime_label=eligibility_regime or "UNKNOWN",
                regime_allowed=regime_allowed,
                regime_policy=regime_policy,
                regime_source="institutional_regime",
                effective_regimes=effective_regimes,
                market_context_daily_trend_vol=market_context_daily_trend_vol,
                market_context_source=market_context_source,
                market_context_vocabulary=market_context_vocabulary,
                classifier_version=institutional["classifier_version"],
                institutional_regime_audit=institutional,
            )
            self._current_strategy_eligibility = eligibility.model_dump(mode="json")

            self.decisions.save_decision(
                self.run_id,
                "strategy_eligibility",
                None,
                {"gate": eligibility.model_dump(mode="json")},
            )
            self.decisions.save_gate_result(
                self.run_id,
                eligibility,
                strategy=strategy_id,
            )

            self.eligibility_alerts.evaluate(
                run_id=self.run_id,
                eligibility=eligibility.model_dump(mode="json"),
                notify=self._send_eligibility_alert,
            )
            if not eligibility.passed:
                return self._finish_cycle(
                    status="strategy_eligibility_rejected",
                    features=features,
                    data_quality=data_quality,
                    iv_history=iv_history,
                    gates=[eligibility],
                    extra={
                        "strategy_id": "iron_condor_monitor",
                        "rejection_reason": eligibility.reason,
                        "position_outcomes": position_outcomes,
                        "persisted_option_rows": persisted_rows,
                        "evidence": evidence,
                    },
                )

        proposal, gates = self.strategy.evaluate(
            snapshot,
            features,
            iv_history_count=iv_history_count,
        )

        if proposal:
            self.decisions.save_gate_results(
                self.run_id,
                proposal,
                gates,
            )

        if proposal is None:
            return self._finish_cycle(
                status="no_proposal",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                gates=gates,
                extra={
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                },
            )

        self.decisions.save_decision(
            self.run_id,
            "signal",
            proposal,
            {
                "gates": [gate.model_dump(mode="json") for gate in gates],
                "proposal": proposal.model_dump(mode="json"),
            },
        )

        regime_limits = self._apply_regime_limits(
            current_regime=canonical_regime_for_risk(evidence) or "UNKNOWN",
            regime_policy=regime_policy,
        )

        regime_risk_decision = self.risk.apply_regime_limits(
            proposal=proposal,
            features=features,
            regime_limits=regime_limits,
        )
        self.decisions.save_risk_decision(
            self.run_id,
            proposal,
            regime_risk_decision,
        )
        if not regime_risk_decision.approved:
            return self._finish_cycle(
                status="regime_risk_rejected",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "reasons": regime_risk_decision.reasons,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                },
            )

        if self.settings.safety.dry_run:
            self.decisions.save_decision(
                self.run_id,
                "dry_run_order_skipped",
                proposal,
                {"would_submit": True},
            )

            return self._finish_cycle(
                status="dry_run",
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                },
            )

        order = self.broker.submit(proposal)
        self._persist_order(order)

        if order.status.value != "FILLED":
            return self._finish_cycle(
                status=order.status.value,
                features=features,
                data_quality=data_quality,
                iv_history=iv_history,
                proposal=proposal,
                extra={
                    "proposal_id": proposal.proposal_id,
                    "reason": order.reject_reason,
                    "position_outcomes": position_outcomes,
                    "persisted_option_rows": persisted_rows,
                    "evidence": evidence,
                    "stale_marks": total_stale_marks,
                },
            )

        strategy_position, leg_positions = self._open_positions(
            proposal,
            order,
        )

        new_position_stale_marks = self._mark_positions(
            strategy_position=strategy_position,
            leg_positions=leg_positions,
            snapshot=snapshot,
        )

        total_stale_marks += new_position_stale_marks

        return self._finish_cycle(
            status="paper_filled",
            features=features,
            data_quality=data_quality,
            iv_history=iv_history,
            proposal=proposal,
            extra={
                "proposal_id": proposal.proposal_id,
                "strategy_position_id": strategy_position.strategy_position_id,
                "exit_reason": None,
                "position_outcomes": position_outcomes,
                "persisted_option_rows": persisted_rows,
                "evidence": evidence,
                "stale_marks": total_stale_marks,
            },
        )

    def _build_features(
        self, snapshot: ChainSnapshot, instrument_token: int
    ) -> tuple[MarketFeatures, int, dict[str, Any]]:
        iv_history = self.store.latest_iv_history(snapshot.underlying)

        spot_history = self.store.latest_spot_closes(
            instrument_token=instrument_token,
            interval="1m",
            limit=60,
        )

        features = build_features(
            snapshot,
            iv_history,
            spot_history,
        )

        market_regime = self.store.get_market_regime_as_of(
            symbol=snapshot.underlying,
            ts=snapshot.ts,
        )

        current_regime = market_regime["regime"] if market_regime else "UNKNOWN"

        regime_policy = self.store.latest_regime_policy(
            symbol=snapshot.underlying,
            as_of=snapshot.ts,
        )

        profile = cast(
            IronCondorProfileSettings,
            self.settings.get_strategy_profile("iron_condor_monitor"),
        )

        effective_regimes, _regime_source, _policy_status = resolve_effective_regimes(
            profile,
            learned_policy=regime_policy,
        )

        context = DecisionContext(
            run_id=self.run_id,
            symbol=snapshot.underlying,
            ts=snapshot.ts,
            features=features,
            snapshot=snapshot,
            iv_history_count=len(iv_history),
            current_regime=current_regime,
            effective_regimes=effective_regimes,
            regime_policy=regime_policy,
            spot_instrument_token=instrument_token,
        )

        evidence_results = self.evidence_runner.run(context)
        evidence = {result.plugin: result.payload for result in evidence_results}
        evidence_pins: dict[str, str] = {}
        for result in evidence_results:
            evidence_id = self.store.write_decision_evidence(
                run_id=self.run_id,
                ts=context.ts,
                symbol=context.symbol,
                plugin=result.plugin,
                evidence=result.payload,
            )
            if result.plugin == "institutional_regime":
                evidence_pins[result.plugin] = evidence_id
        evidence["_decision_evidence_pins"] = evidence_pins

        strategy_id = self._resolve_active_strategy_id()
        timing_filter = self._resolve_timing_filter(strategy_id)

        timing_result = timing_filter.evaluate(evidence.get("multi_timeframe_trend"))

        evidence["timing_filter"] = {
            "strategy_id": strategy_id,
            "filter_name": timing_result.filter_name,
            "filter_version": timing_result.filter_version,
            "mode": timing_result.mode.value,
            "status": timing_result.status.value,
            "alignment": timing_result.alignment,
            "size_multiplier": timing_result.size_multiplier,
            "reasons": timing_result.reasons,
            "details": timing_result.details,
        }
        evidence["variance_risk_premium"] = self._evaluate_vrp(
            strategy_id=strategy_id,
            features=features,
            snapshot=snapshot,
            instrument_token=instrument_token,
        )

        # Derived decision evidence is persisted alongside plugin evidence so
        # every decision can be replayed from decision_evidence alone.
        for plugin_name in ("timing_filter", "variance_risk_premium"):
            self.store.write_decision_evidence(
                run_id=self.run_id,
                ts=context.ts,
                symbol=context.symbol,
                plugin=plugin_name,
                evidence=evidence[plugin_name],
            )

        return features, len(iv_history), evidence

    def _finish_cycle(
        self,
        status: str,
        features: MarketFeatures,
        data_quality: dict[str, Any],
        iv_history: dict[str, Any],
        **details: Any,
    ) -> dict[str, Any]:
        proposal = details.get("proposal")
        gates = cast(list[Any] | None, details.get("gates"))
        extra = dict(cast(dict[str, Any] | None, details.get("extra")) or {})

        # Stage 1 audit: every decision that reached evidence retains regime,
        # RV/VRP, timing-filter, provenance, and outcome fields (charter s7/s8).
        cycle_evidence = extra.get("evidence")
        if isinstance(cycle_evidence, dict) and cycle_evidence:
            extra.setdefault("timing_filter", cycle_evidence.get("timing_filter"))
            extra.setdefault("variance_risk_premium", cycle_evidence.get("variance_risk_premium"))
            extra["decision_audit"] = self._decision_audit(status=status, evidence=cycle_evidence)

        kill_switch_active = self.kill_switch.is_active()

        eligibility_gate = next(
            (gate for gate in (gates or []) if getattr(gate, "gate", None) == "strategy_eligibility"),
            None,
        )

        strategy_eligibility = (
            eligibility_gate.model_dump(mode="json")
            if eligibility_gate is not None
            else getattr(self, "_current_strategy_eligibility", None)
        )
        self.decisions.save_decision(
            self.run_id,
            status,
            proposal,
            {
                "gates": [gate.model_dump(mode="json") for gate in (gates or [])],
                "proposal": (proposal.model_dump(mode="json") if proposal is not None else None),
                **(extra or {}),
            },
        )

        write_live_snapshot(
            build_snapshot(
                features=features,
                open_positions=self.positions.get_open_strategy_positions(),
                kill_switch_active=kill_switch_active,
                loop_status=status,
                data_quality=data_quality,
                iv_history=iv_history,
                strategy_eligibility=strategy_eligibility,
            ),
            snapshot_path=self._live_snapshot_path,
        )

        return {
            "status": status,
            **(extra or {}),
            "gates": [gate.model_dump(mode="json") for gate in (gates or [])],
        }

    @staticmethod
    def _quote_lookup(
        snapshot: ChainSnapshot,
    ) -> dict[tuple[str, float], OptionQuote]:
        return {
            (
                quote.instrument.option_type.value,
                quote.instrument.strike,
            ): quote
            for quote in snapshot.quotes
        }

    def _persist_order(self, order: PaperOrder) -> None:
        self.store.conn.execute(
            """
            INSERT OR REPLACE INTO orders VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                order.order_id,
                datetime.now(UTC),
                self.run_id,
                order.proposal_id,
                order.strategy,
                "PaperBroker",
                order.status.value,
                order.limit_price,
                order.filled_price,
                order.filled_at,
                order.reject_reason,
                order.model_dump_json(),
            ],
        )

    def _open_positions(
        self,
        proposal: TradeProposal,
        order: PaperOrder,
    ) -> tuple[StrategyPosition, list[LegPosition]]:
        filled_at = order.filled_at or datetime.now(UTC)
        entry_price = order.filled_price or proposal.entry_limit_price
        if not proposal.legs:
            raise ValueError("Cannot open a position without legs")

        leg_entry_prices: list[float] = []
        for leg in proposal.legs:
            if leg.entry_price is None or leg.entry_price <= 0:
                raise ValueError(f"Missing or invalid entry premium for leg {leg.instrument.tradingsymbol}")
            leg_entry_prices.append(leg.entry_price)

        proposal_payload = proposal.model_dump(mode="json")

        metadata = {
            **proposal.metadata,
            "original_proposal": proposal_payload,
        }

        strategy_position = StrategyPosition(
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            underlying=proposal.underlying,
            expiry=proposal.expiry,
            opened_at=filled_at,
            entry_price=entry_price,
            current_price=entry_price,
            thesis=proposal.thesis,
            metadata=metadata,
        )

        self.positions.create_strategy_position(strategy_position)

        leg_positions: list[LegPosition] = []

        for leg, leg_entry_price in zip(proposal.legs, leg_entry_prices, strict=True):
            leg_position = LegPosition(
                leg_position_id=(f"{strategy_position.strategy_position_id}:{leg.instrument.tradingsymbol}"),
                strategy_position_id=strategy_position.strategy_position_id,
                proposal_id=proposal.proposal_id,
                strategy=proposal.strategy,
                instrument=leg.instrument,
                side=leg.side,
                lots=leg.lots,
                opened_at=filled_at,
                entry_price=leg_entry_price,
                current_price=leg_entry_price,
            )

            self.positions.create_leg_position(leg_position)
            leg_positions.append(leg_position)

        return strategy_position, leg_positions

    def _mark_positions(
        self,
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
        snapshot: ChainSnapshot,
    ) -> int:
        """Update position marks and unrealized P&L from the latest chain snapshot."""
        quote_lookup = self._quote_lookup(snapshot)
        remaining_credit = 0.0
        unrealized_pnl = 0.0
        stale_marks = 0

        for leg_position in leg_positions:
            leg_position.mark_stale = False

            quote = quote_lookup.get(
                (
                    leg_position.instrument.option_type.value,
                    leg_position.instrument.strike,
                )
            )

            mark = self._mark_price(quote)

            if mark is None:
                mark = leg_position.current_price or leg_position.entry_price
                leg_position.mark_stale = True
                stale_marks += 1

            leg_position.current_price = mark

            if leg_position.side == OrderSide.SELL:
                leg_pnl = (leg_position.entry_price - mark) * leg_position.quantity
                remaining_credit += mark * leg_position.quantity
            else:
                leg_pnl = (mark - leg_position.entry_price) * leg_position.quantity
                remaining_credit -= mark * leg_position.quantity

            leg_position.unrealized_pnl = leg_pnl
            unrealized_pnl += leg_pnl

            self.positions.update_leg_position(leg_position)

        strategy_position.current_price = remaining_credit
        strategy_position.unrealized_pnl = unrealized_pnl
        leg_pnl_total = sum(leg_position.unrealized_pnl for leg_position in leg_positions)

        if abs(leg_pnl_total - strategy_position.unrealized_pnl) > 0.01:
            raise ValueError(
                "Strategy unrealized P&L does not match leg-level P&L: "
                f"strategy={strategy_position.unrealized_pnl}, "
                f"legs={leg_pnl_total}"
            )

        self.positions.update_strategy_position(strategy_position)

        return stale_marks

    def handle_kill_switch(self) -> dict[str, Any]:
        """Handle a dashboard or CLI kill switch signal."""
        kill_switch_active = self.kill_switch.is_active()

        write_live_snapshot(
            build_snapshot(
                kill_switch_active=kill_switch_active,
                loop_status="kill_switch_active",
            ),
            snapshot_path=self._live_snapshot_path,
        )

        self.decisions.save_system_event(
            run_id=self.run_id,
            event_type="kill_switch_active",
            payload={
                "reason": "dashboard_or_cli_kill_switch",
            },
        )

        return {
            "status": "kill_switch_active",
            "kill_switch_active": kill_switch_active,
        }

    def handle_loop_error(self, exc: Exception) -> dict[str, Any]:
        payload = {
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

        self.decisions.save_system_event(
            run_id=self.run_id,
            event_type="loop_error",
            payload=payload,
        )

        return {
            "status": "loop_error",
            **payload,
        }

    @staticmethod
    def _mark_price(quote: OptionQuote | None) -> float | None:
        if quote is None:
            return None

        if quote.bid is not None and quote.ask is not None and quote.ask >= quote.bid > 0:
            return (quote.bid + quote.ask) / 2

        return quote.ltp

    def _close_positions(
        self,
        proposal: TradeProposal,
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
        exit_reason: Any,
    ) -> None:
        closed_at = datetime.now(UTC)

        strategy_position.status = StrategyPositionStatus.CLOSED
        strategy_position.closed_at = closed_at
        strategy_position.exit_reason = exit_reason
        strategy_position.realized_pnl = strategy_position.unrealized_pnl
        strategy_position.unrealized_pnl = 0.0

        self.positions.update_strategy_position(strategy_position)

        for leg_position in leg_positions:
            leg_position.status = StrategyPositionStatus.CLOSED
            leg_position.closed_at = closed_at
            leg_position.exit_reason = exit_reason
            leg_position.realized_pnl = leg_position.unrealized_pnl
            leg_position.unrealized_pnl = 0.0

            self.positions.update_leg_position(leg_position)

        review = PostTradeReview(
            strategy_position_id=strategy_position.strategy_position_id,
            proposal_id=proposal.proposal_id,
            strategy=proposal.strategy,
            closed_at=closed_at,
            realized_pnl=strategy_position.realized_pnl,
            exit_reason=exit_reason,
            thesis_status=("VALID" if strategy_position.realized_pnl >= 0 else "INVALID"),
            decision_quality_notes=("Thesis and gate evidence retained in decision history."),
            outcome_notes=("Realized P&L is an outcome measure, not a decision-quality measure."),
        )

        self.positions.save_post_trade_review(review)

    def _monitor_open_positions(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        quality: DataQualityReport,
    ) -> tuple[list[dict[str, Any]], int]:
        kill_switch_active = self.kill_switch.is_active()
        outcomes: list[dict[str, Any]] = []
        total_stale_marks = 0
        for strategy_position in self.positions.get_open_strategy_positions():
            leg_positions = self.positions.get_leg_positions(strategy_position.strategy_position_id)

            if not leg_positions:
                continue

            stale_marks = self._mark_positions(
                strategy_position=strategy_position,
                leg_positions=leg_positions,
                snapshot=snapshot,
            )
            total_stale_marks += stale_marks

            if stale_marks:
                stale_legs = [
                    leg_position.instrument.tradingsymbol for leg_position in leg_positions if leg_position.mark_stale
                ]

                self.decisions.save_system_event(
                    run_id=self.run_id,
                    event_type="stale_position_marks",
                    payload={
                        "strategy_position_id": strategy_position.strategy_position_id,
                        "proposal_id": strategy_position.proposal_id,
                        "strategy": strategy_position.strategy,
                        "underlying": strategy_position.underlying,
                        "snapshot_ts": snapshot.ts.isoformat(),
                        "stale_mark_count": stale_marks,
                        "stale_legs": stale_legs,
                    },
                    proposal=None,
                )

                outcome = {
                    "strategy_position_id": strategy_position.strategy_position_id,
                    "status": "monitored",
                    "stale_marks": stale_marks,
                    "stale_legs": [
                        leg_position.instrument.tradingsymbol
                        for leg_position in leg_positions
                        if leg_position.mark_stale
                    ],
                }

            logger.info(
                "position_marks_completed",
                extra={
                    "strategy_position_id": strategy_position.strategy_position_id,
                    "stale_marks": stale_marks,
                },
            )

            proposal = self._load_proposal(strategy_position)

            if proposal is None:
                outcomes.append(
                    {
                        "strategy_position_id": (strategy_position.strategy_position_id),
                        "status": "missing_proposal",
                    }
                )
                continue

            exit_evaluation = self.exit_engine.evaluate(
                proposal,
                strategy_position,
                leg_positions,
                features,
                kill_switch_active=kill_switch_active,
                risk_breached=False,
                data_stale=not quality.is_usable,
            )

            self.positions.save_exit_evaluation(exit_evaluation)

            outcome = {
                "strategy_position_id": (strategy_position.strategy_position_id),
                "status": "open",
                "selected_exit_reason": (
                    exit_evaluation.selected_reason.value if exit_evaluation.selected_reason else None
                ),
            }

            if exit_evaluation.selected_reason is not None:
                self._close_positions(
                    proposal=proposal,
                    strategy_position=strategy_position,
                    leg_positions=leg_positions,
                    exit_reason=exit_evaluation.selected_reason,
                )

                outcome["status"] = "closed"

            outcomes.append(outcome)

        return outcomes, total_stale_marks

    def _load_proposal(
        self,
        strategy_position: StrategyPosition,
    ) -> TradeProposal | None:
        payload = strategy_position.metadata.get("original_proposal")

        if not payload:
            return None

        return TradeProposal.model_validate(payload)

    def _default_spot_token_resolver(self, symbol: str) -> int:
        resolver = getattr(
            self.provider,
            "resolve_spot_instrument_token",
            None,
        )

        if callable(resolver):
            typed_resolver = cast(Callable[[str], int], resolver)
            return int(typed_resolver(symbol))

        configured_token = self.settings.market_data.index_instrument_tokens.get(symbol)

        if configured_token:
            return int(configured_token)

        raise ValueError(f"No spot instrument token resolver available for {symbol!r}")

    def _monitor_and_exit_only(
        self,
        *,
        symbol: str,
        availability: Any,
        instrument_token: int,
    ) -> dict[str, Any]:

        t0 = time.perf_counter()
        snapshots = self._fetch_chain_snapshots()
        logger.info("chain_snapshots_seconds=%.3f", time.perf_counter() - t0)

        if not snapshots:
            return {
                "status": "no_complete_chain_snapshot",
                "symbol": symbol,
                "availability": availability,
            }

        snapshot = snapshots[0]
        persisted_rows = self._persist_snapshot(snapshot)

        features, _iv_history_count, evidence = self._build_features(
            snapshot,
            instrument_token=instrument_token,
        )
        quality = self.quality_checker.assess(snapshot)

        position_outcomes = self._monitor_open_positions(
            snapshot=snapshot,
            features=features,
            quality=quality,
        )

        return {
            "status": "monitoring_open_positions",
            "symbol": symbol,
            "availability": availability.overall_status.value,
            "position_outcomes": position_outcomes,
            "persisted_option_rows": persisted_rows,
            "evidence": evidence,
        }

    def _fetch_chain_snapshots(self) -> list[ChainSnapshot]:
        """Return chain snapshots from the configured snapshot source.

        Uses chain_snapshot_provider when supplied; otherwise the injected
        provider. Providers exposing only get_chain_snapshot() are wrapped.
        """
        source = self.chain_snapshot_provider or self.provider
        many = getattr(source, "get_chain_snapshots", None)
        if callable(many):
            return list(cast(Callable[[], list[ChainSnapshot]], many)())
        single = cast(Callable[[], ChainSnapshot], source.get_chain_snapshot)
        return [single()]

    def _persist_snapshot(self, snapshot: ChainSnapshot) -> int:
        """Persist a directly fetched snapshot; persisted sources are not re-written."""
        if not self._persist_fetched_snapshots:
            return 0
        return int(self.store.write_option_stream(self.run_id, snapshot))

    def _resolve_spot_instrument_token(self, symbol: str) -> int:
        if self._spot_instrument_token_resolver is None:
            raise ValueError("A spot_instrument_token_resolver is required to evaluate feature availability")

        return int(self._spot_instrument_token_resolver(symbol))

    def _apply_regime_limits(
        self,
        *,
        current_regime: str,
        regime_policy: dict[str, Any] | None,
    ) -> RegimeRiskLimits:
        if not is_canonical_regime_label(current_regime):
            return RegimeRiskLimits(
                regime="UNKNOWN",
                allowed=False,
                max_lots_per_order=0,
                max_open_positions=0,
                max_notional_exposure=0.0,
                max_portfolio_vega=0.0,
                max_daily_loss=0.0,
                reason="non_canonical_regime",
            )

        profile = self.settings.get_strategy_profile("iron_condor_monitor")
        configured_allowlist = set(profile.regime_policy.allowed_regimes)
        configured_blocklist = set(profile.regime_policy.blocked_regimes)
        if current_regime not in configured_allowlist or current_regime in configured_blocklist:
            return RegimeRiskLimits(
                regime=current_regime,
                allowed=False,
                max_lots_per_order=0,
                max_open_positions=0,
                max_notional_exposure=0.0,
                max_portfolio_vega=0.0,
                max_daily_loss=0.0,
                reason="regime_not_in_configured_allowlist",
            )

        configured_limits = self.settings.get_effective_risk_settings("iron_condor_monitor")
        if (
            not isinstance(regime_policy, dict)
            or regime_policy.get("selection_status") != "READY"
            or regime_policy.get("regime_vocabulary") != "canonical_v1"
        ):
            return RegimeRiskLimits(
                regime=current_regime,
                allowed=True,
                max_lots_per_order=configured_limits.max_lots_per_order,
                max_open_positions=configured_limits.max_open_positions,
                max_notional_exposure=configured_limits.max_notional_exposure,
                max_portfolio_vega=configured_limits.max_portfolio_vega,
                max_daily_loss=configured_limits.max_daily_loss,
                reason="STATIC_CONFIGURED_FALLBACK",
            )

        rejection = canonical_risk_rejection(current_regime, regime_policy)
        if rejection is not None:
            return RegimeRiskLimits(
                regime=current_regime,
                allowed=False,
                max_lots_per_order=0,
                max_open_positions=0,
                max_notional_exposure=0.0,
                max_portfolio_vega=0.0,
                max_daily_loss=0.0,
                reason=rejection,
            )

        regime_limits_config = regime_policy["risk_limits"].get(current_regime) if regime_policy else None

        if regime_limits_config:
            regime_limits = RegimeRiskLimits(
                regime=current_regime,
                allowed=bool(regime_limits_config.get("allowed", False)),
                max_lots_per_order=int(regime_limits_config["max_lots_per_order"]),
                max_open_positions=int(regime_limits_config["max_open_positions"]),
                max_notional_exposure=float(regime_limits_config["max_notional_exposure"]),
                max_portfolio_vega=float(regime_limits_config["max_portfolio_vega"]),
                max_daily_loss=float(regime_limits_config["max_daily_loss"]),
                reason=str(regime_limits_config.get("reason", "CONFIGURED")),
            )
        else:
            regime_limits = build_regime_risk_limits(
                regime=current_regime,
                policy=self._policy_from_lookup(regime_policy),
                base_limits=self.settings.risk,
            )
        return regime_limits

    @staticmethod
    def _policy_from_lookup(
        regime_policy: dict[str, Any] | None,
    ) -> Any:
        if regime_policy is None:
            return RegimePolicy(
                allowed_regimes=frozenset(),
                regime_metrics={},
                selection_status="INSUFFICIENT_TRAIN_DATA",
            )

        return RegimePolicy(
            allowed_regimes=frozenset(regime_policy["allowed_regimes"]),
            regime_metrics=regime_policy.get("regime_metrics", {}),
            selection_status=regime_policy["selection_status"],
        )

    def _evaluate_strategy_eligibility(
        self,
        *,
        profile: IronCondorProfileSettings,
        features: MarketFeatures,
        iv_history_count: int,
        regime_label: str,
        regime_allowed: bool,
        regime_policy: dict[str, Any] | None,
        regime_source: str,
        market_context_daily_trend_vol: str | None = None,
        market_context_source: str | None = None,
        market_context_vocabulary: str | None = None,
        effective_regimes: list[str] | None = None,
        classifier_version: str | None = None,
        institutional_regime_audit: dict[str, Any] | None = None,
    ) -> GateResult:
        iv_rank = features.iv_rank
        iv_rank_available = iv_rank is not None
        iv_rank_valid = iv_rank_available and math.isfinite(iv_rank) and 0.0 <= iv_rank <= 100.0

        require_iv_rank = profile.regime_policy.require_iv_rank_available
        minimum_iv_history = self.settings.analytics.min_iv_history_observations
        iv_analytics = features.iv_analytics

        checks = {
            "strategy_id": "iron_condor_monitor",
            "profile_enabled": profile.enabled,
            "underlying_allowed": (self.settings.market_data.default_symbol in profile.underlyings),
            "regime_label": regime_label,
            "regime_label_source": regime_source,
            "regime_allowed": regime_allowed,
            "allowed_regimes": sorted(effective_regimes or []),
            "regime_classifier_version": classifier_version,
            "regime_registry_version": REGIME_REGISTRY_VERSION,
            "institutional_regime_evidence": {
                "available": (institutional_regime_audit or {}).get("available", False),
                "complete": (institutional_regime_audit or {}).get("complete", False),
                "regime_label_canonical": (institutional_regime_audit or {}).get("regime_label_canonical", False),
                "regime_label_eligible": (institutional_regime_audit or {}).get("regime_label_eligible", False),
                "thresholds_provisional": (institutional_regime_audit or {}).get("thresholds_provisional"),
                "decision_eligibility_asserted": (institutional_regime_audit or {}).get(
                    "decision_eligibility_asserted"
                ),
                "as_of": (institutional_regime_audit or {}).get("as_of"),
                "missing_components": (institutional_regime_audit or {}).get("missing_components", []),
                "reason": (institutional_regime_audit or {}).get("reason"),
            },
            "market_context": {
                "daily_trend_vol": market_context_daily_trend_vol,
                "source": market_context_source,
                "regime_vocabulary": market_context_vocabulary,
            },
            "intraday_shape": features.intraday_shape.value,
            "iv_history_count": iv_history_count,
            "minimum_iv_history": minimum_iv_history,
            "iv_history_available": iv_history_count >= minimum_iv_history,
            "current_iv": iv_analytics.current_iv if iv_analytics else None,
            "iv_min": iv_analytics.iv_min if iv_analytics else None,
            "iv_max": iv_analytics.iv_max if iv_analytics else None,
            "valid_iv_history_count": (iv_analytics.valid_history_count if iv_analytics else 0),
            "iv_rank": features.iv_rank,
            "iv_rank_available": features.iv_rank is not None,
            "iv_rank_valid": iv_rank_valid,
            "iv_rank_required": require_iv_rank,
            "iv_rank_calculation_version": (iv_analytics.calculation_version if iv_analytics else None),
        }

        reasons: list[str] = []

        if not profile.enabled:
            reasons.append("strategy profile disabled")

        if not checks["underlying_allowed"]:
            reasons.append("underlying not allowed by strategy profile")

        if not regime_allowed:
            reasons.append(f"IV regime not allowed: {regime_label}")

        if require_iv_rank and not iv_rank_available:
            reasons.append("IV rank unavailable")

        if iv_rank_available and not iv_rank_valid:
            reasons.append("IV rank outside valid range")

        if not checks["iv_history_available"]:
            reasons.append("IV history below minimum required observations")

        passed = not reasons

        return GateResult(
            gate="strategy_eligibility",
            passed=passed,
            reason=("strategy eligibility satisfied" if passed else "; ".join(reasons)),
            details=checks,
        )

    def _send_eligibility_alert(self, message: str) -> None:
        if not self.settings.notifier.enabled:
            return

        if not self.settings.notifier.telegram.enabled:
            return
        notifier = Notifier()
        notifier.send(message)

    @staticmethod
    def build_expected_move_diagnostics(
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Build diagnostics explaining the expected-move calculation."""

        now = now or datetime.now(UTC)

        if not snapshot.quotes:
            return {
                "spot": snapshot.spot,
                "atm_strike": None,
                "atm_iv": None,
                "nearest_expiry": None,
                "dte_days": None,
                "expected_move_points": features.expected_move_points,
                "implied_annualised_iv_from_expected_move": None,
                "error": "no_option_quotes",
            }

        atm_strike = min(
            (quote.instrument.strike for quote in snapshot.quotes),
            key=lambda strike: abs(strike - snapshot.spot),
        )

        atm_ivs = [
            quote.iv for quote in snapshot.quotes if quote.instrument.strike == atm_strike and quote.iv is not None
        ]

        atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else None

        nearest_expiry = min(quote.instrument.expiry for quote in snapshot.quotes)

        dte_days = max(
            (nearest_expiry - now.date()).days,
            0,
        )

        implied_iv = None

        if features.expected_move_points and snapshot.spot and dte_days > 0:
            implied_iv = features.expected_move_points / snapshot.spot / (dte_days / 365) ** 0.5 * 100

        return {
            "spot": snapshot.spot,
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "nearest_expiry": nearest_expiry.isoformat(),
            "dte_days": dte_days,
            "expected_move_points": features.expected_move_points,
            "implied_annualised_iv_from_expected_move": implied_iv,
        }

    def _evaluate_vrp(
        self,
        *,
        strategy_id: str,
        features: MarketFeatures,
        snapshot: ChainSnapshot,
        instrument_token: int,
    ) -> dict[str, Any]:
        """Evaluate VRP using a point-in-time HAR-RV forecast.

        HAR-RV is fitted to complete 5-minute intraday realized variance plus
        the prior-session-close to current-session-open overnight return.
        Near-expiry ATM IV remains diagnostic only: the charter requires a
        30-day constant-maturity IV series before the gate can pass.
        """
        profile = self.settings.get_strategy_profile(strategy_id)
        if not isinstance(profile, IronCondorProfileSettings):
            return {
                "applicable": False,
                "strategy_id": strategy_id,
                "calculation_version": VRP_CALCULATION_VERSION,
                "reason": "vrp_gate_not_applicable_to_strategy_type",
            }

        gate = profile.vrp_gate
        snapshot_ts = snapshot.ts if snapshot.ts.tzinfo else snapshot.ts.replace(tzinfo=UTC)
        session_start = datetime.combine(snapshot_ts.astimezone(IST).date(), dt_time.min, tzinfo=IST)
        cache_key = (instrument_token, session_start.date())
        expected_rv: float | None
        rv_details: dict[str, Any]
        calibration: dict[str, Any]
        cached = self._har_rv_cache.get(cache_key)
        if cached is not None:
            expected_rv, rv_details, calibration = cached
        else:
            source_start = session_start - timedelta(days=550)
            configured_holidays = set(self.settings.trading_calendar.closed_dates)
            for year_holidays in NSE_HOLIDAYS.values():
                configured_holidays.update(year_holidays)
            calendar = NSETradingCalendar(closed_dates=configured_holidays)
            candle_reader = getattr(self.store, "completed_one_minute_candles", None)
            minute_candles = (
                candle_reader(
                    instrument_token=instrument_token,
                    start=source_start,
                    before=session_start,
                    limit=210000,
                )
                if callable(candle_reader)
                else []
            )
            source_digest = hashlib.sha256()
            for candle_ts, candle_open, candle_close in minute_candles:
                source_digest.update(
                    (f"{candle_ts.isoformat()}|{float(candle_open).hex()}|{float(candle_close).hex()}\\n").encode()
                )
            rv_details = {
                "method": HAR_RV_METHOD,
                "version": HAR_RV_VERSION,
                "horizon_days": HAR_RV_HORIZON_DAYS,
                "measure": HAR_RV_MEASURE,
                "is_forecast": True,
                "gate_eligible": False,
                "diagnostic_only": True,
                "source_table": "spot_candles",
                "source_interval": "1m",
                "derived_interval": "5m",
                "instrument_token": instrument_token,
                "source_start": source_start.isoformat(),
                "source_before": session_start.isoformat(),
                "source_minute_rows": len(minute_candles),
                "source_first_minute_ts": minute_candles[0][0].isoformat() if minute_candles else None,
                "source_last_minute_ts": minute_candles[-1][0].isoformat() if minute_candles else None,
                "source_data_sha256": source_digest.hexdigest(),
                "expected_minute_rows_per_session": 375,
                "five_minute_observations_per_session": 75,
            }
            expected_rv = None
            calibration = {
                "reason": "har_rv_observations_unavailable",
                "diagnostic_only": True,
                "gate_margin_eligible": False,
            }
            try:
                observations = build_daily_rv_observations(
                    minute_candles,
                    calendar=calendar,
                    as_of=snapshot_ts,
                )
                daily_variances = [item.realized_variance for item in observations]
                expected_rv, forecast_details = forecast_har_rv_30d(daily_variances)
                calibration = calibrate_har_rv_forecast_errors(daily_variances)
                rv_details.update(forecast_details)
                calibration_margin_value = calibration.get("absolute_error_p90")
                calibration_eligible = (
                    calibration.get("gate_margin_eligible") is True
                    and calibration.get("version") == HAR_RV_CALIBRATION_VERSION
                    and isinstance(calibration.get("samples"), int)
                    and not isinstance(calibration.get("samples"), bool)
                    and calibration.get("samples", 0) >= CALIBRATION_MINIMUM_SAMPLES
                    and isinstance(calibration_margin_value, (int, float))
                    and not isinstance(calibration_margin_value, bool)
                    and math.isfinite(float(calibration_margin_value))
                    and float(calibration_margin_value) >= 0.0
                )
                rv_details["calibration_gate_eligible"] = calibration_eligible
                rv_details["gate_eligible"] = expected_rv is not None and calibration_eligible
                rv_details["diagnostic_only"] = not rv_details["gate_eligible"]
                rv_details["complete_sessions"] = len(observations)
                rv_details["first_session_date"] = observations[0].session_date.isoformat() if observations else None
                rv_details["last_session_date"] = observations[-1].session_date.isoformat() if observations else None
                rv_details["last_session_close_ts"] = (
                    observations[-1].last_minute_ts.isoformat() if observations else None
                )
                rv_details["calibration"] = calibration
                last_session_age = (session_start.date() - observations[-1].session_date).days if observations else None
                rv_details["last_complete_session_age_days"] = last_session_age
                rv_details["max_daily_close_age_days"] = gate.max_daily_close_age_days
                if last_session_age is None or last_session_age > gate.max_daily_close_age_days:
                    expected_rv = None
                    rv_details["gate_eligible"] = False
                    rv_details["diagnostic_only"] = True
                    rv_details["reason"] = "stale_or_missing_complete_intraday_sessions"
            except (ValueError, TypeError) as exc:
                rv_details["reason"] = f"intraday_rv_input_rejected:{exc}"
            self._har_rv_cache[cache_key] = (expected_rv, rv_details, calibration)

        # Preserve the former close-to-close series strictly as an auditable
        # fallback diagnostic. It is never supplied to the VRP evaluator.
        daily = self.store.completed_daily_closes(
            instrument_token=instrument_token,
            before=session_start,
            limit=gate.rv_window_days + 1,
        )
        trailing_rv, trailing_details = trailing_daily_realized_volatility(
            [close for _ts, close in daily],
            window_days=gate.rv_window_days,
        )
        trailing_details["last_close_ts"] = daily[-1][0].isoformat() if daily else None
        rv_details["trailing_close_to_close_fallback"] = {
            **trailing_details,
            "value": trailing_rv,
            "used_for_gate": False,
        }

        calibration_margin_value = calibration.get("absolute_error_p90")
        calibration_margin = (
            float(calibration_margin_value)
            if rv_details.get("calibration_gate_eligible") is True
            and isinstance(calibration_margin_value, (int, float))
            and not isinstance(calibration_margin_value, bool)
            else None
        )
        effective_minimum_vrp = gate.minimum_vrp + (calibration_margin or 0.0)
        har_identity: dict[str, Any] = {}
        if expected_rv is not None and calibration_margin is not None:
            har_identity = {
                "expected_realized_volatility_method": HAR_RV_METHOD,
                "expected_realized_volatility_version": HAR_RV_VERSION,
                "expected_realized_volatility_horizon_days": HAR_RV_HORIZON_DAYS,
                "expected_realized_volatility_measure": HAR_RV_MEASURE,
                "expected_realized_volatility_is_forecast": True,
                "expected_realized_volatility_calibration_is_eligible": True,
                "expected_realized_volatility_calibration_version": str(calibration["version"]),
                "expected_realized_volatility_calibration_samples": int(calibration["samples"]),
                "expected_realized_volatility_calibration_margin": calibration_margin,
            }
        result = evaluate_variance_risk_premium(
            implied_volatility=features.atm_iv,
            expected_realized_volatility=expected_rv,
            minimum_vrp=effective_minimum_vrp,
            configured_minimum_vrp=gate.minimum_vrp,
            implied_volatility_source="features.atm_iv",
            implied_volatility_is_30d_constant_maturity=False,
            **har_identity,
        )
        return {
            "applicable": True,
            "strategy_id": strategy_id,
            "calculation_version": result.calculation_version,
            "available": result.available,
            "passed": result.passed,
            "estimator_gate_eligible": result.details.get("estimator_gate_eligible", False),
            "implied_volatility_gate_eligible": result.details.get("implied_volatility_gate_eligible", False),
            "gate_passed": result.available and result.passed,
            "gate_mode": EvidenceMode.HARD_GATE.value,
            "minimum_vrp": effective_minimum_vrp,
            "configured_minimum_vrp": gate.minimum_vrp,
            "forecast_error_margin": calibration_margin,
            "implied_volatility": result.implied_volatility,
            "implied_volatility_input": {
                "source": "features.atm_iv",
                "basis": "near_expiry_atm",
                "constant_maturity_30d": False,
                "as_of": features.ts.isoformat(),
            },
            "expected_realized_volatility": expected_rv,
            "expected_realized_variance": result.expected_realized_variance,
            "expected_realized_volatility_input": rv_details,
            "variance_risk_premium": result.variance_risk_premium,
            "reasons": result.reasons,
            "details": result.details,
        }

    def _decision_audit(self, *, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """Build the replayable Stage 1 decision-audit record."""
        timing = evidence.get("timing_filter") or {}
        vrp = evidence.get("variance_risk_premium") or {}
        provenance: dict[str, Any] = {}
        for plugin, payload in evidence.items():
            if plugin.startswith("_") or not isinstance(payload, dict):
                continue
            provenance[plugin] = {
                "available": payload.get("available"),
                "complete": payload.get("complete"),
                "as_of": payload.get("as_of"),
                "version": (
                    payload.get("classifier_version")
                    or payload.get("calculation_version")
                    or payload.get("filter_version")
                    or payload.get("version")
                ),
                "mode": payload.get("mode") or payload.get("gate_mode"),
            }
        regime_audit = self._institutional_regime_audit(evidence)
        evidence_pins = evidence.get("_decision_evidence_pins")
        if isinstance(evidence_pins, dict):
            regime_audit["evidence_id"] = evidence_pins.get("institutional_regime")
        return {
            "audit_version": "stage1_decision_audit_v1",
            "decision_outcome": status,
            "run_id": self.run_id,
            "regime": regime_audit,
            "realized_volatility_input": vrp.get("expected_realized_volatility_input"),
            "variance_risk_premium": {
                "applicable": vrp.get("applicable"),
                "calculation_version": vrp.get("calculation_version"),
                "available": vrp.get("available"),
                "value": vrp.get("variance_risk_premium"),
                "implied_volatility": vrp.get("implied_volatility"),
                "expected_realized_volatility": vrp.get("expected_realized_volatility"),
                "expected_realized_volatility_input": vrp.get("expected_realized_volatility_input"),
                "estimator_gate_eligible": vrp.get("estimator_gate_eligible"),
                "implied_volatility_gate_eligible": vrp.get("implied_volatility_gate_eligible"),
                "estimator_details": vrp.get("details"),
                "minimum_vrp": vrp.get("minimum_vrp"),
                "configured_minimum_vrp": vrp.get("configured_minimum_vrp"),
                "forecast_error_margin": vrp.get("forecast_error_margin"),
                "gate_passed": vrp.get("gate_passed"),
                "reasons": vrp.get("reasons"),
            },
            "timing_filter": {
                "filter_name": timing.get("filter_name"),
                "filter_version": timing.get("filter_version"),
                "mode": timing.get("mode"),
                "status": timing.get("status"),
                "size_multiplier": timing.get("size_multiplier"),
                "reasons": timing.get("reasons"),
            },
            "evidence_provenance": provenance,
            "paper_trading": self.settings.safety.paper_trading,
            "dry_run": self.settings.safety.dry_run,
            "decision_eligibility_asserted": False,
        }

    @staticmethod
    def _institutional_regime_audit(evidence: dict[str, Any]) -> dict[str, Any]:
        """Extract the canonical-regime audit fields from institutional evidence."""
        payload = evidence.get("institutional_regime")
        institutional = payload if isinstance(payload, dict) else {}
        label = institutional.get("regime_label")
        available = institutional.get("available") is True
        complete = institutional.get("complete") is True
        thresholds_approved = institutional.get("thresholds_provisional") is False
        eligibility_not_asserted = institutional.get("decision_eligibility_asserted") is False
        canonical = is_canonical_regime_label(label)
        eligible = (
            available
            and complete
            and thresholds_approved
            and eligibility_not_asserted
            and canonical
        )
        return {
            "regime_label": label,
            "regime_label_canonical": canonical,
            "regime_label_eligible": eligible,
            "available": available,
            "complete": complete,
            "thresholds_provisional": institutional.get("thresholds_provisional"),
            "decision_eligibility_asserted": institutional.get("decision_eligibility_asserted"),
            "classifier_version": institutional.get("classifier_version"),
            "regime_registry_version": REGIME_REGISTRY_VERSION,
            "as_of": institutional.get("as_of"),
            "complete": bool(institutional.get("complete")),
            "missing_components": institutional.get("missing_components") or [],
            "reason": institutional.get("reason") if institutional else "institutional_regime_evidence_missing",
        }

    def _resolve_active_strategy_id(self) -> str:
        allowed_strategy_ids = self.settings.safety.allowed_strategies

        if not allowed_strategy_ids:
            raise ValueError("No allowed strategies configured")

        enabled_strategy_ids = [
            strategy_id
            for strategy_id in allowed_strategy_ids
            if self.settings.get_strategy_profile(strategy_id).enabled
        ]

        if len(enabled_strategy_ids) != 1:
            raise ValueError(
                "Exactly one enabled strategy must be active; "
                f"found {len(enabled_strategy_ids)}: {sorted(enabled_strategy_ids)}"
            )

        return enabled_strategy_ids[0]

    def _resolve_timing_filter(self, strategy_id: str) -> MultiTimeframeTimingFilter:
        profile = self.settings.get_strategy_profile(strategy_id)
        timing_settings = getattr(profile, "timing_filter", None)

        if timing_settings is None or not timing_settings.enabled:
            return MultiTimeframeTimingFilter(mode=EvidenceMode.OBSERVATION)

        return MultiTimeframeTimingFilter(
            mode=timing_settings.mode,
            min_trend_strength=timing_settings.min_trend_strength,
            required_timeframes=tuple(timing_settings.required_timeframes),
        )
