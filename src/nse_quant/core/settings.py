"""Typed global settings with precedence: .env > YAML > defaults."""

from __future__ import annotations

import os
from datetime import date as Date
from datetime import time
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path("config")
SETTINGS_YAML = CONFIG_DIR / "settings.yaml"
Path(os.getenv("NSE_QUANT_SETTINGS", str(CONFIG_DIR / "settings.yaml")))


class SafetySettings(BaseModel):
    dry_run: bool = True
    trading_enabled: bool = False
    paper_trading: bool = True
    allowed_strategies: list[str] = Field(default_factory=lambda: ["iron_condor_monitor"])


class UniverseSettings(BaseModel):
    underlying: str = "NIFTY"
    strikes_per_side: int = 10


class RuntimeSettings(BaseModel):
    stale_seconds: float = 300.0
    loop_interval_seconds: int = 15
    market_closed_wait_seconds: int = 60
    enforce_market_hours: bool = True
    allow_out_of_hours_testing: bool = False


class StorageSettings(BaseModel):
    db_path: Path = Path("data/nse_quant.duckdb")
    parquet_dir: Path = Path("data/parquet")
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8050
    db_memory_limit: str = "512MB"
    db_threads: int = 2


class AnalyticsSettings(BaseModel):
    risk_free_rate: float = 0.07
    rv_window: int = 20
    iv_history_limit: int = 250
    min_iv_rank: float = 40
    min_iv_rv_spread: float = 0.02
    max_expected_move_buffer: float = 1.15
    min_iv_history_observations: int = 30
    allow_iv_rank_cold_start: bool = True
    expiries_per_snapshot: int = 2

    sma20_window: int = 20
    sma50_window: int = 50
    atr14_window: int = 14

    @model_validator(mode="after")
    def validate_analytics(self) -> Self:
        if self.min_iv_history_observations < 1:
            raise ValueError("min_iv_history_observations must be >= 1")

        if self.iv_history_limit < self.min_iv_history_observations:
            raise ValueError("iv_history_limit must be >= min_iv_history_observations")

        return self

    @model_validator(mode="after")
    def validate_feature_windows(self) -> Self:
        if self.sma20_window >= self.sma50_window:
            raise ValueError("sma20_window must be smaller than sma50_window")

        if self.sma50_window < 2:
            raise ValueError("sma50_window must be at least 2")

        if self.atr14_window < 2:
            raise ValueError("atr14_window must be at least 2")

        return self


class RegimePolicySettings(BaseModel):
    allowed_regimes: list[str] = Field(default_factory=list)
    blocked_regimes: list[str] = Field(default_factory=list)
    require_iv_rank_available: bool = True


class StrategyRiskSettings(BaseModel):
    max_lots_per_order: int = 2
    max_open_positions: int = 1
    max_daily_loss: float = 25_000
    max_notional_exposure: float = 2_000_000
    max_spread_pct: float = 0.03


class StrategyExitSettings(BaseModel):
    profit_target_pct: float = 50.0
    stop_loss_credit_multiple: float = 2.0
    theta_decay_target_pct: float = 50.0
    iv_collapse_pct: float = 20.0
    data_quality_max_age_seconds: int = 30
    expected_move_violation_buffer: float = 1.25


class StrategyProfileSettings(BaseModel):
    enabled: bool = False
    strategy_type: str
    underlyings: list[str] = Field(default_factory=lambda: ["NIFTY"])
    min_iv_rank: float | None = None
    regime_policy: RegimePolicySettings = Field(default_factory=RegimePolicySettings)
    risk: StrategyRiskSettings = Field(default_factory=StrategyRiskSettings)
    exits: StrategyExitSettings = Field(default_factory=StrategyExitSettings)


class IronCondorProfileSettings(StrategyProfileSettings):
    strategy_type: str = "iron_condor"
    wing_distance_points: float = 200.0
    min_credit: float = 20.0
    min_days_to_expiry: int = 1


STRATEGY_PROFILE_TYPES: dict[str, type[StrategyProfileSettings]] = {
    "iron_condor": IronCondorProfileSettings,
}


class RiskSettings(BaseModel):
    max_lots_per_order: int = 2
    max_open_positions: int = 3
    max_notional_exposure: float = 2_000_000
    max_daily_loss: float = 25_000
    max_portfolio_delta: float = 100
    max_portfolio_vega: float = 5_000
    max_portfolio_gamma: float = 0.01
    max_spread_pct: float = 0.03
    min_oi: int = 50_000
    min_volume: int = 500


class ExitSettings(BaseModel):
    theta_decay_target_pct: float = 50
    iv_collapse_pct: float = 20
    data_quality_max_age_seconds: int = 30
    expected_move_violation_buffer: float = 1.25


class EventRiskSettings(BaseModel):
    enabled: bool = False
    block_new_entries: bool = False
    lookahead_minutes: int = 0
    blackout_minutes_before: int = 30
    blackout_minutes_after: int = 30
    high_impact_types: list[str] = Field(
        default_factory=lambda: ["RBI_POLICY", "FED_POLICY", "UNION_BUDGET"]
    )


class PaperExecutionSettings(BaseModel):
    fill_slippage_pct: float = 0.0
    allow_partial_fills: bool = False


class ResearchAlertSettings(BaseModel):
    enabled: bool = False
    min_alert_severity: str = "ALERT"


class TelegramNotifierSettings(BaseModel):
    enabled: bool = True
    uri: str = "https://api.telegram.org/bot{token}/sendMessage"
    message_length_limit: int = 4096


class NotifierSettings(BaseModel):
    enabled: bool = True
    telegram: TelegramNotifierSettings = Field(default_factory=TelegramNotifierSettings)
    research_alerts: ResearchAlertSettings = Field(default_factory=ResearchAlertSettings)


class CandleIntervalSettings(BaseModel):
    kite_interval: str


class MarketDataSettings(BaseModel):
    default_symbol: str = "NIFTY"
    risk_free_rate: float = 0.065

    index_symbols: list[str] = Field(
        default_factory=lambda: [
            "NIFTY",
            "BANKNIFTY",
            "FINNIFTY",
            "MIDCPNIFTY",
        ]
    )

    spot_quote_keys: dict[str, str] = Field(
        default_factory=lambda: {
            "NIFTY": "NSE:NIFTY 50",
            "BANKNIFTY": "NSE:NIFTY BANK",
            "FINNIFTY": "NSE:FINNIFTY",
            "MIDCPNIFTY": "NSE:MIDCPNIFTY",
        }
    )

    index_instrument_symbols: dict[str, str] = Field(
        default_factory=lambda: {
            "NIFTY": "NIFTY 50",
            "BANKNIFTY": "NIFTY BANK",
            "FINNIFTY": "FINNIFTY",
            "MIDCPNIFTY": "MIDCPNIFTY",
        }
    )

    index_instrument_tokens: dict[str, int] = Field(default_factory=dict)

    candle_intervals: dict[str, CandleIntervalSettings] = Field(
        default_factory=lambda: {
            "1m": CandleIntervalSettings(kite_interval="minute"),
            "15m": CandleIntervalSettings(kite_interval="15minute"),
            "60m": CandleIntervalSettings(kite_interval="60minute"),
            "day": CandleIntervalSettings(kite_interval="day"),
        }
    )


class KiteSecrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_user_id: str = ""
    kite_password: str = ""
    kite_totp_secret: str = ""
    kite_auth_mode: str = "manual"
    kite_access_token: str = ""
    kite_redirect_uri: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class SpecialSessionSettings(BaseModel):
    session_date: Date
    open_time: time
    close_time: time
    session_type: str


class TradingCalendarSettings(BaseModel):
    closed_dates: list[Date] = Field(default_factory=list)
    special_sessions: list[SpecialSessionSettings] = Field(default_factory=list)


class BacktestReadinessSettings(BaseModel):
    min_complete_days: int = 20
    min_iv_rv_aligned_days: int = 10
    min_regime_days: int = 10


class ResearchSettings(BaseModel):
    enforce_feature_availability: bool = True
    enforce_regime_policy: bool = True
    enforce_strategy_eligibility: bool = True
    min_history_observations: int = 1
    enable_parameter_experiments: bool = False
    backtest_readiness: BacktestReadinessSettings = Field(default_factory=BacktestReadinessSettings)


class WalkForwardSettings(BaseModel):
    train_days: int = 252
    test_days: int = 63
    step_days: int = 63
    min_train_trades: int = 10
    min_test_trades: int = 5

    @model_validator(mode="after")
    def validate_windows(self) -> WalkForwardSettings:
        if self.train_days <= 0:
            raise ValueError("train_days must be positive")
        if self.test_days <= 0:
            raise ValueError("test_days must be positive")
        if self.step_days <= 0:
            raise ValueError("step_days must be positive")
        if self.step_days > self.test_days:
            raise ValueError("step_days must not exceed test_days")

        return self


class MultiTimeframeEvidenceSettings(BaseModel):
    enabled: bool = True
    timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "15m", "60m"],
        min_length=1,
    )
    history_limit: int = 6000


class TechnicalIndicatorSettings(BaseModel):
    enabled: bool = False
    timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "15m", "60m"],
    )
    history_limit: int = 6000
    rsi_period: int = 14
    adx_period: int = 14
    ema_periods: list[int] = Field(
        default_factory=lambda: [9, 20, 50, 200],
    )


class VolumeFlowSettings(BaseModel):
    enabled: bool = False
    timeframes: list[str] = Field(
        default_factory=lambda: ["1m", "15m", "60m"],
    )
    history_limit: int = 6000
    baseline_periods: int = 30


class OptionPositioningSettings(BaseModel):
    enabled: bool = False
    pcr_high_threshold: float = 1.25
    pcr_low_threshold: float = 0.75
    iv_crush_decline_pct: float = 20.0
    history_limit: int = 100


class MarketStructureSettings(BaseModel):
    enabled: bool = False
    timeframes: list[str] = Field(
        default_factory=lambda: ["15m", "60m", "day"],
    )
    history_limit: int = 6000
    swing_lookback: int = 2
    opening_range_minutes: int = 15


class MarketContextSettings(BaseModel):
    enabled: bool = False

    symbols: list[str] = Field(
        default_factory=lambda: ["NIFTY", "BANKNIFTY"],
        min_length=1,
    )

    max_age_seconds: int = Field(
        default=86_400,
        gt=0,
    )

    @model_validator(mode="after")
    def validate_symbols(self) -> Self:
        if any(not symbol.strip() or symbol != symbol.strip() for symbol in self.symbols):
            raise ValueError(
                "market_context.symbols must contain non-empty symbols"
                "symbols without surrounding whitespace"
            )

        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("market_context.symbols must not contain duplicates")

        return self


class ExecutionQualitySettings(BaseModel):
    enabled: bool = False
    max_quote_age_seconds: int = Field(default=300, gt=0)


class InstitutionalRegimeSettings(BaseModel):
    enabled: bool = False

    iv_history_limit: int = Field(default=250, ge=2)
    min_iv_history_observations: int = Field(default=30, ge=2)

    high_iv_rank_threshold: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_iv_history(self) -> Self:
        if self.iv_history_limit < self.min_iv_history_observations:
            raise ValueError("iv_history_limit must be >= min_iv_history_observations")

        return self


class EvidencePluginsSettings(BaseModel):
    multi_timeframe: MultiTimeframeEvidenceSettings = MultiTimeframeEvidenceSettings()
    event_risk: EventRiskSettings = EventRiskSettings()
    technical_indicators: TechnicalIndicatorSettings = TechnicalIndicatorSettings()
    volume_flow: VolumeFlowSettings = VolumeFlowSettings()
    option_positioning: OptionPositioningSettings = OptionPositioningSettings()
    market_structure: MarketStructureSettings = MarketStructureSettings()
    market_context: MarketContextSettings = Field(default_factory=MarketContextSettings)
    execution_quality: ExecutionQualitySettings = Field(default_factory=ExecutionQualitySettings)
    institutional_regime: InstitutionalRegimeSettings = Field(
        default_factory=InstitutionalRegimeSettings
    )


class EvidenceSettings(BaseModel):
    enabled: bool = True
    plugins: EvidencePluginsSettings = EvidencePluginsSettings()


class DebugSettings(BaseModel):
    enable_option_stream_diagnostics: bool = False


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a mapping")
    return value


class Settings(BaseSettings):
    """Inherits from BaseSettings to correctly process environmental variables and YAML loading."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",  # Allows setting secrets via SECRETS__KITE_API_KEY
    )

    safety: SafetySettings = Field(default_factory=SafetySettings)
    universe: UniverseSettings = Field(default_factory=UniverseSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    exits: ExitSettings = Field(default_factory=ExitSettings)
    paper_execution: PaperExecutionSettings = Field(default_factory=PaperExecutionSettings)
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)
    secrets: KiteSecrets = Field(default_factory=KiteSecrets)
    trading_calendar: TradingCalendarSettings = Field(default_factory=TradingCalendarSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    strategies: dict[str, IronCondorProfileSettings] = Field(default_factory=dict)
    walk_forward: WalkForwardSettings = Field(default_factory=WalkForwardSettings)
    evidence: EvidenceSettings = Field(default_factory=EvidenceSettings)
    debug: DebugSettings = Field(default_factory=DebugSettings)

    @model_validator(mode="before")
    @classmethod
    def validate_safety_before(cls, data: Any) -> Any:
        """Validates incoming configuration data before the full model object is instantiated."""
        if not isinstance(data, dict):
            return data

        # Extract sub-dictionaries or use defaults if keys are missing
        safety = data.get("safety", {})
        runtime = data.get("runtime", {})
        analytics = data.get("analytics", {})
        risk = data.get("risk", {})

        # 1. Check Safety Rules
        # Handle both dictionary objects and pre-parsed instances (if mixed in tests)
        trading_enabled = (
            safety.get("trading_enabled", False)
            if isinstance(safety, dict)
            else getattr(safety, "trading_enabled", False)
        )
        dry_run = (
            safety.get("dry_run", True)
            if isinstance(safety, dict)
            else getattr(safety, "dry_run", True)
        )
        paper_trading = (
            safety.get("paper_trading", True)
            if isinstance(safety, dict)
            else getattr(safety, "paper_trading", True)
        )

        if trading_enabled and (dry_run or paper_trading):
            raise ValueError("Live mode requires DRY_RUN=false and PAPER_TRADING=false")
        if trading_enabled:
            raise ValueError("Live trading is blocked in this milestone")

        # 2. Check Runtime Timing
        stale_seconds = (
            runtime.get("stale_seconds", 15.0)
            if isinstance(runtime, dict)
            else getattr(runtime, "stale_seconds", 15.0)
        )
        loop_interval_seconds = (
            runtime.get("loop_interval_seconds", 15)
            if isinstance(runtime, dict)
            else getattr(runtime, "loop_interval_seconds", 15)
        )

        if stale_seconds <= 0 or loop_interval_seconds <= 0:
            raise ValueError("Runtime timing must be positive")

        # 3. Check Analytics Constraints
        min_iv_rank = (
            analytics.get("min_iv_rank", 40)
            if isinstance(analytics, dict)
            else getattr(analytics, "min_iv_rank", 40)
        )
        if not 0 <= min_iv_rank <= 100:
            raise ValueError("min_iv_rank must be 0-100")

        # 4. Check Risk Constraints
        max_lots_per_order = (
            risk.get("max_lots_per_order", 2)
            if isinstance(risk, dict)
            else getattr(risk, "max_lots_per_order", 2)
        )
        if max_lots_per_order < 1:
            raise ValueError("max_lots_per_order must be >=1")

        return data

    @model_validator(mode="after")
    def validate_candle_intervals(self) -> Self:
        if not self.market_data.candle_intervals:
            raise ValueError("market_data.candle_intervals must not be empty")

        for interval, config in self.market_data.candle_intervals.items():
            if not interval:
                raise ValueError("Candle interval keys must be non-empty")
            if not config.kite_interval:
                raise ValueError(f"kite_interval must be configured for interval {interval!r}")

        return self

    def get_strategy_profile(
        self,
        strategy_id: str,
    ) -> StrategyProfileSettings:
        profile = self.strategies.get(strategy_id)

        if profile is None:
            raise ValueError(f"No strategy profile configured: {strategy_id!r}")

        return profile

    @model_validator(mode="after")
    def validate_strategy_profiles(self) -> Self:
        for strategy_id, profile in self.strategies.items():
            expected_type = STRATEGY_PROFILE_TYPES.get(profile.strategy_type)

            if expected_type is None or not isinstance(profile, expected_type):
                raise ValueError(
                    f"Strategy {strategy_id!r} has invalid strategy_type {profile.strategy_type!r}"
                )

            if strategy_id in self.safety.allowed_strategies and not profile.enabled:
                raise ValueError(
                    f"Strategy {strategy_id!r} is enabled in "
                    "safety.allowed_strategies but its profile is disabled"
                )

            overlap = set(profile.regime_policy.allowed_regimes) & set(
                profile.regime_policy.blocked_regimes
            )

            if overlap:
                raise ValueError(
                    f"Strategy {strategy_id!r} has overlapping allowed "
                    f"and blocked regimes: {sorted(overlap)}"
                )

        return self

    @model_validator(mode="before")
    @classmethod
    def normalize_strategy_profiles(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        strategies = data.get("strategies")
        if not isinstance(strategies, dict):
            return data

        normalized: dict[str, Any] = {}
        for strategy_id, profile in strategies.items():
            if isinstance(profile, StrategyProfileSettings):
                normalized[strategy_id] = profile
                continue

            if not isinstance(profile, dict):
                raise TypeError(f"strategies.{strategy_id} must be a mapping")

            strategy_type = profile.get("strategy_type")
            if not isinstance(strategy_type, str):
                raise TypeError(
                    f"Unknown strategy_type {strategy_type!r} for strategy {strategy_id!r}"
                )

            profile_type = STRATEGY_PROFILE_TYPES.get(strategy_type)

            if profile_type is None:
                raise ValueError(
                    f"Unknown strategy_type {strategy_type!r} for strategy {strategy_id!r}"
                )

            normalized[strategy_id] = profile_type(**profile)

        data["strategies"] = normalized
        return data

    def get_effective_risk_settings(
        self,
        strategy_id: str,
    ) -> RiskSettings:
        profile = self.get_strategy_profile(strategy_id)
        effective = self.risk.model_copy(deep=True)

        profile_risk = profile.risk.model_dump(exclude_unset=True)

        for key, value in profile_risk.items():
            if hasattr(effective, key):
                setattr(effective, key, value)

        return effective

    def get_effective_exit_settings(
        self,
        strategy_id: str,
    ) -> ExitSettings:
        profile = self.get_strategy_profile(strategy_id)
        effective = self.exits.model_copy(deep=True)

        profile_exits = profile.exits.model_dump(exclude_unset=True)

        for key, value in profile_exits.items():
            if hasattr(effective, key):
                setattr(effective, key, value)

        return effective

    def get_effective_min_iv_rank(
        self,
        strategy_id: str,
    ) -> float:
        profile = self.get_strategy_profile(strategy_id)

        if profile.min_iv_rank is not None:
            return profile.min_iv_rank

        return self.analytics.min_iv_rank


def load_settings(path: str | Path | None = None) -> Settings:
    # Read the YAML file dictionary
    yaml_data = _load_yaml(Path(path) if path else SETTINGS_YAML)

    # BaseSettings automatically merges kwargs, files, and environment variables
    return Settings(**yaml_data)


def get_settings(path: str | Path | None = None) -> Settings:
    """Return validated settings. Kept as a function for testability."""
    return load_settings(path) if path is not None else settings


settings = load_settings()
