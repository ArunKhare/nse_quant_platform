"""Diagnose why the Oct. 27 replay produced no proposals.
$env:NSE_QUANT_SETTINGS = "config/settings.test.yaml"
uv run python scripts/debug_oct27_gates.py
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from zoneinfo import ZoneInfo

from nse_quant.core.models import OptionType
from nse_quant.core.settings import get_settings
from nse_quant.research.backtest.config import BacktestConfig
from nse_quant.research.backtest.engine import BacktestEngine
from nse_quant.strategy.iron_condor import IronCondorMonitor

ist = ZoneInfo("Asia/Kolkata")

settings = get_settings("config/settings.test.yaml")

print(
    "settings:",
    f"min_iv_rank={settings.analytics.min_iv_rank}",
    f"max_spread_pct={settings.get_effective_risk_settings('iron_condor_monitor').max_spread_pct}",
)


def print_required_legs(
    *,
    engine: BacktestEngine,
    oct27_steps: list,
) -> None:
    sample = oct27_steps[0].snapshot
    atm = sample.atm_strike()
    wing = engine.strategy.config.wing_distance_points
    strategy = engine.strategy

    print(
        "strategy settings:",
        f"min_iv_rank={strategy.settings.analytics.min_iv_rank}",
        f"gate_min_iv_rank={strategy.gates.iv_regime_gate.settings.analytics.min_iv_rank}",
        f"liquidity_max_spread={strategy.gates.liquidity_gate.risk_limits.max_spread_pct}",
    )

    available = {(quote.instrument.option_type, quote.instrument.strike) for quote in sample.quotes}

    print(f"Sample ATM: {atm}, wing: {wing}")
    print(
        f"Available strikes: {sorted({quote.instrument.strike for quote in sample.quotes})}",
    )

    required = {
        OptionType.PE: [
            atm - wing,
            atm - 2 * wing,
        ],
        OptionType.CE: [
            atm + wing,
            atm + 2 * wing,
        ],
    }

    print("Required legs:")
    for option_type, strikes in required.items():
        for strike in strikes:
            print(
                f"  {option_type.value} {strike}: available={(option_type, strike) in available}",
            )


def print_leg_liquidity(
    *,
    engine: BacktestEngine,
    oct27_steps: list,
) -> None:
    sample = oct27_steps[0].snapshot
    atm = sample.atm_strike()
    wing = engine.strategy.config.wing_distance_points
    # strategy = engine.strategy

    required = [
        (OptionType.PE, atm - wing),
        (OptionType.PE, atm - 2 * wing),
        (OptionType.CE, atm + wing),
        (OptionType.CE, atm + 2 * wing),
    ]

    quotes = {
        (quote.instrument.option_type, quote.instrument.strike): quote for quote in sample.quotes
    }

    print("\nRequired-leg liquidity:")

    for option_type, strike in required:
        quote = quotes.get((option_type, strike))

        if quote is None:
            print(f"  {option_type.value} {strike}: MISSING")
            continue

        print(
            f"  {option_type.value} {strike}: "
            f"ltp={quote.ltp} "
            f"bid={quote.bid} "
            f"ask={quote.ask} "
            f"spread_pct={quote.spread_pct} "
            f"oi={quote.oi} "
            f"volume={quote.volume}",
        )


def main() -> int:
    config = BacktestConfig(
        warehouse_dir="data/exports",
        output_dir="data/research/debug_oct27_gates",
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 27),
        run_id="debug_oct27_gates",
        iv_collapse_pct=10.0,
        expected_move_buffer=0.75,
        entry_cooldown_minutes=30,
    )

    print(
        "DEBUG config:",
        f"start={config.start_date}",
        f"end={config.end_date}",
        f"min_snapshots={config.min_snapshots}",
        f"min_iv_coverage={config.min_iv_coverage}",
    )

    engine = BacktestEngine(
        config,
        strategy=IronCondorMonitor(settings),
    )
    snapshots = engine.loader.load_market_hour_snapshots()

    print(f"Loaded snapshots: {len(snapshots)}")

    prepared = engine.prepare_features(snapshots)

    if not prepared:
        print("No prepared feature steps")
        return 1

    oct27_steps = [step for step in prepared if step.snapshot.ts.date() == date(2026, 10, 27)]

    print(f"Oct 27 steps: {len(oct27_steps)}")

    if not oct27_steps:
        print("No Oct 27 steps found")
        return 1

    first_oct27 = oct27_steps[0]

    print("\nFirst Oct 27 features:")
    print(first_oct27.features)
    print(f"IV history count: {first_oct27.iv_history_count}")

    print_required_legs(
        engine=engine,
        oct27_steps=oct27_steps,
    )
    print_leg_liquidity(
        engine=engine,
        oct27_steps=oct27_steps,
    )
    failure_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    date_gate_counts: Counter[tuple[date, str]] = Counter()

    for step in prepared:
        _, gates = engine.strategy.evaluate(
            step.snapshot,
            step.features,
            iv_history_count=step.iv_history_count,
        )

        for gate in gates:
            if not gate.passed:
                failure_counts[gate.gate] += 1
                reason_counts[f"{gate.gate}: {gate.reason}"] += 1
                date_gate_counts[(step.snapshot.ts.date(), gate.gate)] += 1

    print("\nFailed gate counts:")
    for gate, count in failure_counts.most_common():
        print(f"  {gate}: {count}")

    print("\nFailed gate reasons:")
    for reason, count in reason_counts.most_common(20):
        print(f"  {count:5d}  {reason}")

    print("\nFailures by date and gate:")
    for (trade_date, gate), count in sorted(date_gate_counts.items()):
        print(f"  {trade_date} {gate}: {count}")

    proposal_count = 0
    first_proposal = None
    credit_failures = 0
    proposal_gate_failures: Counter[str] = Counter()

    for step in oct27_steps:
        proposal, gates = engine.strategy.evaluate(
            step.snapshot,
            step.features,
            iv_history_count=step.iv_history_count,
        )

        if proposal is not None:
            proposal_count += 1
            if first_proposal is None:
                first_proposal = proposal
            continue

        for gate in gates:
            if not gate.passed:
                proposal_gate_failures[gate.gate] += 1
                if gate.gate == "minimum_credit":
                    credit_failures += 1

    print("\nOct 27 proposal diagnostics:")
    print(f"  proposals: {proposal_count}")
    print(f"  minimum_credit failures: {credit_failures}")
    print("  gate failures after long-wing selection:")
    for gate, count in proposal_gate_failures.most_common():
        print(f"    {gate}: {count}")

    if first_proposal is not None:
        print("\nFirst proposal:")
        print(first_proposal.model_dump(mode="json"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
