"""Paper decision loop: market data to post-trade review.


Flow:
market data -> analytics -> feature snapshot -> open-position monitoring
-> strategy proposal -> gates -> risk check -> paper order
-> independent leg positions -> marking/P&L -> exit evaluation
-> close -> post-trade review.
"""


from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from nse_quant.analytics.features import build_features
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
from nse_quant.core.settings import IronCondorProfileSettings, get_settings
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
from nse_quant.research.evidence_plugins.multi_timeframe import MultiTimeframeTrendPlugin
from nse_quant.research.evidence_plugins.registry import EvidencePluginRunner
from nse_quant.research.regime_policy import RegimePolicy
from nse_quant.research.regime_policy_evaluation import (
    resolve_effective_regimes,
)
from nse_quant.research.regime_risk_policy import RegimeRiskLimits, build_regime_risk_limits
from nse_quant.risk.risk_engine import RiskEngine
from nse_quant.strategy.exit_engine import ExitEngine
from nse_quant.strategy.iron_condor import IronCondorMonitor


class DecisionLoop:
    def __init__(
        self,
        store: Any,
        provider: Any,
        broker: PaperBroker,
        run_id: str,
        settings: Any | None = None,
        spot_instrument_token_resolver: Callable[[str], int] | None = None,
        feature_gate: SpotFeatureGate | None = None,
        live_snapshot_path: Path | None = None,
        kill_switch: KillSwitch | None = None

    ) -> None:
        self.settings = settings or get_settings()
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

        self.evidence_runner = EvidencePluginRunner(plugins)
        self.provider = provider
        self.broker = broker
        self.run_id = run_id
        self.feature_store = FeatureStore(store.conn)
        self.decisions = DecisionRepository(store.conn)
        self.positions = PositionRepository(store.conn)
        self.risk = RiskEngine(
            store.conn,
            self.settings,
            self.positions,
            risk_settings=self.settings.risk,
        )
        self.exit_engine = ExitEngine(
            self.settings.get_effective_exit_settings(
                "iron_condor_monitor"
            )
        )
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
        self._spot_instrument_token_resolver = (
            spot_instrument_token_resolver
            or self._default_spot_token_resolver
        )
        self.availability_checker = FeatureAvailabilityChecker(store)
        self._live_snapshot_path = live_snapshot_path
        self.eligibility_alerts = EligibilityAlertManager(self.decisions)
        self.kill_switch = kill_switch or KillSwitch()

    def run_once(self) -> dict[str, Any]:
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

        current_regime = "UNKNOWN"
        regime_policy: dict[str, Any] | None = None

        self.store.write_feature_availability_result(
            gate_result_id=uuid4().hex,
            ts=datetime.now(UTC),
            run_id=self.run_id,
            symbol=symbol,
            passed=availability.core_status
            == FeatureAvailability.READY,
            reasons=availability.reasons,
            checks={
                "core_status": availability.core_status.value,
                "htf_status": availability.htf_status.value,
                "iv_status": availability.iv_status.value,
                "overall_status": availability.overall_status.value,
                "observations": availability.observations,
                "missing": availability.missing,
                "enforced": (
                    self.settings.research.enforce_feature_availability
                ),
            },
        )

        availability_enforced = (
            self.settings.research.enforce_feature_availability
        )

        if (
            availability_enforced
            and availability.core_status != FeatureAvailability.READY):
            return {
                "status": "feature_availability_rejected",
                "symbol": symbol,
                "reasons": availability.reasons,
                "checks": {
                    "core_status": availability.core_status.value,
                    "htf_status": availability.htf_status.value,
                    "iv_status": availability.iv_status.value,
                    "overall_status": (
                        availability.overall_status.value
                    ),
                },
            }

        if (
            availability_enforced
            and not availability.can_evaluate_new_entries
        ):
            open_positions = self.positions.get_open_strategy_positions()

            if not open_positions:
                return {
                    "status": "warming_up",
                    "symbol": symbol,
                    "reasons": availability.reasons,
                    "checks": {
                        "overall_status": (
                            availability.overall_status.value
                        ),
                        "observations": availability.observations,
                    },
                }

            # Continue only through open-position monitoring/exits.
            return self._monitor_and_exit_only(
                symbol=symbol,
                availability=availability,
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
                "evidence": {}
            }

        snapshot = self.provider.get_chain_snapshot()
        persisted_rows = self.store.write_option_stream(
            self.run_id,
            snapshot,
        )

        features, iv_history_count, evidence = self._build_features(snapshot)

        # Diagnostics
        expected_move_inputs = self.build_expected_move_diagnostics(
            snapshot=snapshot,
            features=features,
        )

        features.diagnostics["expected_move_inputs"] = (
            expected_move_inputs
        )

        quality: DataQualityReport = self.quality_checker.assess(snapshot)
        position_outcomes = self._monitor_open_positions(
            snapshot=snapshot,
            features=features,
            quality=quality,
        )

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

        iv_smile = [
            {
                "strike": quote.instrument.strike,
                "option_type": quote.instrument.option_type.value,
                "iv": quote.iv,
            }
            for quote in snapshot.quotes
            if quote.iv is not None
        ]

        features.diagnostics["iv_smile"] = iv_smile

        iv_history = {
            "observation_count": iv_history_count,
            "minimum_required": (
                self.settings.analytics.min_iv_history_observations
            ),
            "mode": (
                "ENFORCED"
                if iv_history_count
                >= self.settings.analytics.min_iv_history_observations
                else "COLD_START"
            ),
        }

        profile = self.settings.get_strategy_profile(
            "iron_condor_monitor"
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

        if self.settings.research.enforce_strategy_eligibility:
            market_regime = self.store.get_market_regime_as_of(
                symbol=symbol,
                ts=features.ts,
            )
            current_regime = market_regime["regime"] if market_regime else "UNKNOWN"
            regime_policy = self.store.latest_regime_policy(
                symbol=symbol,
                as_of=features.ts,
            )

            strategy_id = "iron_condor_monitor"
            profile = self.settings.get_strategy_profile(strategy_id)

            if not isinstance(profile, IronCondorProfileSettings):
                raise TypeError(
                    f"{strategy_id!r} must use IronCondorProfileSettings"
                )

            effective_regimes, _regime_source, _policy_status = (
                resolve_effective_regimes(
                    profile,
                    learned_policy=regime_policy,
                )
            )

            regime_allowed = current_regime in effective_regimes

            eligibility = self._evaluate_strategy_eligibility(
                profile=profile,
                features=features,
                iv_history_count=iv_history_count,
                current_regime=current_regime,
                regime_allowed=regime_allowed,
                regime_policy=regime_policy,
            )

            self.decisions.save_decision(
                self.run_id,
                "strategy_eligibility",
                None,
                {"gate": eligibility.model_dump(mode="json")},
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


        regime_policy_enforced = (
            self.settings.research.enforce_regime_policy
        )

        if regime_policy_enforced:
            market_regime = self.store.get_market_regime_as_of(
                symbol=symbol,
                ts=features.ts,
            )

            current_regime = (
                market_regime["regime"]
                if market_regime
                else "UNKNOWN"
            )


            regime_policy = self.store.latest_regime_policy(
                symbol=symbol,
                as_of=features.ts,
            )

            allowed_regimes = (
                regime_policy["allowed_regimes"]
                if regime_policy
                else set()
            )

            policy_allows = (
                regime_policy is not None
                and regime_policy["selection_status"] != "READY"
                and current_regime in allowed_regimes
            )

            if not policy_allows:
                self.decisions.save_gate_results(
                    self.run_id,
                    proposal,
                    [
                        GateResult(
                            gate="regime_policy",
                            passed=False,
                            reason=(
                                "no_active_policy"
                                if regime_policy is None
                                else "regime_not_allowed"
                            ),
                            details={
                                "regime": current_regime,
                                "allowed_regimes": sorted(
                                    allowed_regimes
                                ),
                                "policy_status": (
                                    regime_policy["selection_status"]
                                    if regime_policy
                                    else None
                                ),
                            },
                        )
                    ],
                )

                return self._finish_cycle(
                    status="regime_policy_rejected",
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

            regime_limits = self._apply_regime_limits(
                current_regime=current_regime,
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

        if (
            self.settings.safety.dry_run
        ):
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
                },
            )

        strategy_position, leg_positions = self._open_positions(
            proposal,
            order,
        )

        self._mark_positions(
            strategy_position=strategy_position,
            leg_positions=leg_positions,
            snapshot=snapshot,
        )

        # print(
        #     "Spread mark diagnostics:",
        #     "entry=", strategy_position.entry_price,
        #     "current=", strategy_position.current_price,
        #     "legs=", [
        #         {
        #             "symbol": leg.instrument.tradingsymbol,
        #             "side": leg.side.value,
        #             "entry": leg.entry_price,
        #             "current": leg.current_price,
        #             "quantity": leg.quantity,
        #         }
        #         for leg in leg_positions
        #     ],
        # )

        exit_evaluation = self.exit_engine.evaluate(
            proposal,
            strategy_position,
            leg_positions,
            features,
            kill_switch_active=False,
            risk_breached=False,
            data_stale=not quality.is_usable,
        )

        self.positions.save_exit_evaluation(exit_evaluation)

        if exit_evaluation.selected_reason is not None:
            self._close_positions(
                proposal=proposal,
                strategy_position=strategy_position,
                leg_positions=leg_positions,
                exit_reason=exit_evaluation.selected_reason,
            )

        return self._finish_cycle(
            status="paper_filled",
            features=features,
            data_quality=data_quality,
            iv_history=iv_history,
            proposal=proposal,
            extra={
                "proposal_id": proposal.proposal_id,
                "strategy_position_id": strategy_position.strategy_position_id,
                "exit_reason": (
                    exit_evaluation.selected_reason.value
                    if exit_evaluation.selected_reason
                    else None
                ),
                "position_outcomes": position_outcomes,
                "persisted_option_rows": persisted_rows,
                "evidence": evidence,
            },
        )

    def _build_features(
        self,
        snapshot: ChainSnapshot,
    ) -> tuple[MarketFeatures, int, dict[str, Any]]:
        iv_history = self.store.latest_iv_history(snapshot.underlying)

        instrument_token = self._spot_instrument_token_resolver(
            snapshot.underlying
        )

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

        current_regime = (
            market_regime["regime"]
            if market_regime
            else "UNKNOWN"
        )

        regime_policy = self.store.latest_regime_policy(
            symbol=snapshot.underlying,
            as_of=snapshot.ts,
        )

        profile = self.settings.get_strategy_profile(
            "iron_condor_monitor"
        )

        effective_regimes, _regime_source, _policy_status = (
            resolve_effective_regimes(
                profile,
                learned_policy=regime_policy,
            )
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

        evidence = self.evidence_runner.run(context)

        return features, len(iv_history), evidence

    def _finish_cycle(
        self,
        status: str,
        features: MarketFeatures,
        data_quality: dict[str, Any],
        iv_history: dict[str, Any],
        proposal: TradeProposal | None = None,
        gates: list[Any] | None = None,
        extra: dict[str, Any] | None = None,
        *,
        kill_switch_active: bool | None = None
    ) -> dict[str, Any]:
        kill_switch_active =(
            self.kill_switch.is_active()
            if kill_switch_active is None
            else kill_switch_active
        )
        eligibility_gate = next(
            (
                gate
                for gate in (gates or [])
                if getattr(gate, "gate", None) == "strategy_eligibility"
            ),
            None,
        )

        strategy_eligibility = (
            eligibility_gate.model_dump(mode="json")
            if eligibility_gate is not None
            else None
        )
        self.decisions.save_decision(
            self.run_id,
            status,
            proposal,
            {
                "gates": [
                    gate.model_dump(mode="json")
                    for gate in (gates or [])
                ],
                "proposal": (
                    proposal.model_dump(mode="json")
                    if proposal is not None
                    else None
                ),
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
            "gates": [
                gate.model_dump(mode="json")
                for gate in (gates or [])
            ],
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

        for leg in proposal.legs:
            leg_position = LegPosition(
                leg_position_id=(
                    f"{strategy_position.strategy_position_id}:"
                    f"{leg.instrument.tradingsymbol}"
                ),
                strategy_position_id=strategy_position.strategy_position_id,
                proposal_id=proposal.proposal_id,
                strategy=proposal.strategy,
                instrument=leg.instrument,
                side=leg.side,
                lots=leg.lots,
                opened_at=filled_at,
                entry_price=proposal.entry_limit_price / len(proposal.legs),
                current_price=proposal.entry_limit_price / len(proposal.legs),
            )

            self.positions.create_leg_position(leg_position)
            leg_positions.append(leg_position)

        return strategy_position, leg_positions

    def _mark_positions(
        self,
        strategy_position: StrategyPosition,
        leg_positions: list[LegPosition],
        snapshot: ChainSnapshot,
    ) -> None:
        quote_lookup = self._quote_lookup(snapshot)
        strategy_mark = 0.0

        for leg_position in leg_positions:
            quote = quote_lookup.get(
                (
                    leg_position.instrument.option_type.value,
                    leg_position.instrument.strike,
                )
            )

            mark = self._mark_price(quote)

            if mark is None:
                mark = (
                    leg_position.current_price
                    or leg_position.entry_price
                )

            leg_position.current_price = mark

            direction = 1 if leg_position.side == OrderSide.BUY else -1

            leg_position.unrealized_pnl = (
                mark - leg_position.entry_price
            ) * leg_position.quantity * direction

            self.positions.update_leg_position(leg_position)

            strategy_mark += (
                mark
                * leg_position.quantity
                * (1 if leg_position.side == OrderSide.BUY else -1)
            )

        close_cost = -strategy_mark

        strategy_position.current_price = close_cost
        strategy_position.unrealized_pnl = (
            strategy_position.entry_price - close_cost
        )

        self.positions.update_strategy_position(strategy_position)

    def handle_kill_switch(self) -> dict[str, Any]:
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

        if (
            quote.bid is not None
            and quote.ask is not None
            and quote.ask >= quote.bid > 0
        ):
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
            thesis_status=(
                "VALID"
                if strategy_position.realized_pnl >= 0
                else "INVALID"
            ),
            decision_quality_notes=(
                "Thesis and gate evidence retained in decision history."
            ),
            outcome_notes=(
                "Realized P&L is an outcome measure, not a "
                "decision-quality measure."
            ),
        )

        self.positions.save_post_trade_review(review)

    def _monitor_open_positions(
        self,
        snapshot: ChainSnapshot,
        features: MarketFeatures,
        quality: DataQualityReport,
        kill_switch_active: bool | None = None
    ) -> list[dict[str, Any]]:
        kill_switch_active = self.kill_switch.is_active()
        outcomes: list[dict[str, Any]] = []

        for strategy_position in self.positions.get_open_strategy_positions():
            leg_positions = self.positions.get_leg_positions(
                strategy_position.strategy_position_id
            )

            if not leg_positions:
                continue

            self._mark_positions(
                strategy_position=strategy_position,
                leg_positions=leg_positions,
                snapshot=snapshot,
            )

            proposal = self._load_proposal(strategy_position)

            if proposal is None:
                outcomes.append(
                    {
                        "strategy_position_id": (
                            strategy_position.strategy_position_id
                        ),
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
                "strategy_position_id": (
                    strategy_position.strategy_position_id
                ),
                "status": "open",
                "selected_exit_reason": (
                    exit_evaluation.selected_reason.value
                    if exit_evaluation.selected_reason
                    else None
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

        return outcomes

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
            return int(resolver(symbol))  # type: ignore[arg-type]

        configured_token = (
            self.settings.market_data.index_instrument_tokens.get(symbol)
        )

        if configured_token:
            return int(configured_token)

        raise ValueError(
            f"No spot instrument token resolver available for {symbol!r}"
        )

    def _monitor_and_exit_only(
        self,
        *,
        symbol: str,
        availability: Any,
    ) -> dict[str, Any]:
        snapshot = self.provider.get_chain_snapshot()
        persisted_rows = self.store.write_option_stream(
            self.run_id,
            snapshot,
        )

        features, _iv_history_count, evidence = self._build_features(snapshot)
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
            "evidence": evidence
        }

    def _resolve_spot_instrument_token(self, symbol: str) -> int:
        if self._spot_instrument_token_resolver is None:
            raise ValueError(
                "A spot_instrument_token_resolver is required to evaluate "
                "feature availability"
            )

        return int(self._spot_instrument_token_resolver(symbol))

    def _apply_regime_limits(self, *, current_regime:str, regime_policy:dict[str, Any]| None,) -> RegimeRiskLimits:
        regime_limits_config = (
            regime_policy["risk_limits"].get(current_regime)
            if regime_policy
            else None
        )

        if regime_limits_config:
            regime_limits = RegimeRiskLimits(
                regime=current_regime,
                allowed=bool(regime_limits_config.get("allowed", False)),
                max_lots_per_order=int(
                    regime_limits_config["max_lots_per_order"]
                ),
                max_open_positions=int(
                    regime_limits_config["max_open_positions"]
                ),
                max_notional_exposure=float(
                    regime_limits_config["max_notional_exposure"]
                ),
                max_portfolio_vega=float(
                    regime_limits_config["max_portfolio_vega"]
                ),
                max_daily_loss=float(
                    regime_limits_config["max_daily_loss"]
                ),
                reason=str(
                    regime_limits_config.get("reason", "CONFIGURED")
                ),
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
            allowed_regimes=frozenset(
                regime_policy["allowed_regimes"]
            ),
            regime_metrics={},
            selection_status=regime_policy["selection_status"],
        )

    def _evaluate_strategy_eligibility(
        self,
        *,
        profile: IronCondorProfileSettings,
        features: MarketFeatures,
        iv_history_count: int,
        current_regime: str,
        regime_allowed: bool,
        regime_policy: dict[str, Any] | None,
    ) -> GateResult:
        iv_rank_available = features.iv_rank is not None
        require_iv_rank = profile.regime_policy.require_iv_rank_available
        minimum_iv_history = (
            self.settings.analytics.min_iv_history_observations
        )

        checks = {
            "strategy_id": "iron_condor_monitor",
            "profile_enabled": profile.enabled,
            "underlying_allowed": (
                self.settings.market_data.default_symbol
                in profile.underlyings
            ),
            "current_regime": current_regime,
            "regime_allowed": regime_allowed,
            "iv_history_count": iv_history_count,
            "minimum_iv_history": minimum_iv_history,
            "iv_history_available": (
                iv_history_count >= minimum_iv_history
            ),
            "iv_rank": features.iv_rank,
            "iv_rank_available": iv_rank_available,
            "iv_rank_required": require_iv_rank,
        }

        reasons: list[str] = []

        if not profile.enabled:
            reasons.append("strategy profile disabled")

        if not checks["underlying_allowed"]:
            reasons.append("underlying not allowed by strategy profile")

        if not regime_allowed:
            reasons.append(f"IV regime not allowed: {current_regime}")

        if require_iv_rank and not iv_rank_available:
            reasons.append("IV rank unavailable")

        if not checks["iv_history_available"]:
            reasons.append("IV history below minimum required observations")

        passed = not reasons

        return GateResult(
            gate="strategy_eligibility",
            passed=passed,
            reason=(
                "strategy eligibility satisfied"
                if passed
                else "; ".join(reasons)
            ),
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
            (
                quote.instrument.strike
                for quote in snapshot.quotes
            ),
            key=lambda strike: abs(strike - snapshot.spot),
        )

        atm_ivs = [
            quote.iv
            for quote in snapshot.quotes
            if quote.instrument.strike == atm_strike
            and quote.iv is not None
        ]

        atm_iv = (
            sum(atm_ivs) / len(atm_ivs)
            if atm_ivs
            else None
        )

        nearest_expiry = min(
            quote.instrument.expiry
            for quote in snapshot.quotes
        )

        dte_days = max(
            (nearest_expiry - now.date()).days,
            0,
        )

        implied_iv = None

        if (
            features.expected_move_points
            and snapshot.spot
            and dte_days > 0
        ):
            implied_iv = (
                features.expected_move_points
                / snapshot.spot
                / (dte_days / 365) ** 0.5
                * 100
            )

        return {
            "spot": snapshot.spot,
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "nearest_expiry": nearest_expiry.isoformat(),
            "dte_days": dte_days,
            "expected_move_points": features.expected_move_points,
            "implied_annualised_iv_from_expected_move": implied_iv,
        }