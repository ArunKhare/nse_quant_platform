"""Typed global settings with precedence: .env > YAML > defaults."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path("config")
SETTINGS_YAML = CONFIG_DIR / "settings.yaml"

class SafetySettings(BaseModel):
    dry_run: bool = True
    trading_enabled: bool = False
    paper_trading: bool = True
    allowed_strategies: list[str] = Field(default_factory=lambda: ["iron_condor_monitor"])

class UniverseSettings(BaseModel):
    underlying: str = "NIFTY"
    strikes_per_side: int = 10

class RuntimeSettings(BaseModel):
    stale_seconds: float = 15.0
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

    @model_validator(mode="after")
    def validate_analytics(self) -> AnalyticsSettings:
        if self.min_iv_history_observations < 1:
            raise ValueError("min_iv_history_observations must be >= 1")

        if self.iv_history_limit < self.min_iv_history_observations:
            raise ValueError(
                "iv_history_limit must be >= min_iv_history_observations"
            )

        return self
class IronCondorSettings(BaseModel):
    wing_distance_points: float = 200
    min_credit: float = 20

class StrategySettings(BaseModel):
    iron_condor_monitor: IronCondorSettings = Field(default_factory=IronCondorSettings)

class RiskSettings(BaseModel):
    max_lots_per_order: int = 2
    max_open_positions: int = 3
    max_notional_exposure: float = 2_000_000
    max_daily_loss: float = 25_000
    max_portfolio_delta: float = 100
    max_portfolio_vega: float = 5_000
    max_portfolio_gamma: float = .01
    max_spread_pct: float = .03
    min_oi: int = 50_000
    min_volume: int = 500

class ExitSettings(BaseModel):
    theta_decay_target_pct: float = 50
    iv_collapse_pct: float = 20
    data_quality_max_age_seconds: int = 30
    expected_move_violation_buffer: float = 1.25

class PaperExecutionSettings(BaseModel):
    fill_slippage_pct: float = 0.0
    allow_partial_fills: bool = False

class TelegramNotifierSettings(BaseModel):
    enabled: bool = True
    uri: str = "https://api.telegram.org/bot{token}/sendMessage"
    message_length_limit: int = 4096

class MarketDataSettings(BaseModel):
    default_symbol: str = "NIFTY"

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

    intervals: dict[str, str] = Field(
        default_factory=lambda: {
            "1m": "minute",
            "15m": "15minute",
            "60m": "60minute",
            "day": "day",
        }
    )

class NotifierSettings(BaseModel):
    enabled: bool = True
    telegram: TelegramNotifierSettings = Field(default_factory=TelegramNotifierSettings)

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
        env_nested_delimiter="__"  # Allows setting secrets via SECRETS__KITE_API_KEY
    )

    safety: SafetySettings = Field(default_factory=SafetySettings)
    universe: UniverseSettings = Field(default_factory=UniverseSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    exits: ExitSettings = Field(default_factory=ExitSettings)
    paper_execution: PaperExecutionSettings = Field(default_factory=PaperExecutionSettings)
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)
    secrets: KiteSecrets = Field(default_factory=KiteSecrets)

    @model_validator(mode="before")
    @classmethod
    def validate_safety_before(cls, data:Any) -> Any:
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
        trading_enabled = safety.get("trading_enabled", False) if isinstance(safety, dict) else getattr(safety, "trading_enabled", False)
        dry_run = safety.get("dry_run", True) if isinstance(safety, dict) else getattr(safety, "dry_run", True)
        paper_trading = safety.get("paper_trading", True) if isinstance(safety, dict) else getattr(safety, "paper_trading", True)

        if trading_enabled and (dry_run or paper_trading):
            raise ValueError("Live mode requires DRY_RUN=false and PAPER_TRADING=false")
        if trading_enabled:
            raise ValueError("Live trading is blocked in this milestone")

        # 2. Check Runtime Timing
        stale_seconds = runtime.get("stale_seconds", 15.0) if isinstance(runtime, dict) else getattr(runtime, "stale_seconds", 15.0)
        loop_interval_seconds = runtime.get("loop_interval_seconds", 15) if isinstance(runtime, dict) else getattr(runtime, "loop_interval_seconds", 15)

        if stale_seconds <= 0 or loop_interval_seconds <= 0:
            raise ValueError("Runtime timing must be positive")

        # 3. Check Analytics Constraints
        min_iv_rank = analytics.get("min_iv_rank", 40) if isinstance(analytics, dict) else getattr(analytics, "min_iv_rank", 40)
        if not 0 <= min_iv_rank <= 100:
            raise ValueError("min_iv_rank must be 0-100")

        # 4. Check Risk Constraints
        max_lots_per_order = risk.get("max_lots_per_order", 2) if isinstance(risk, dict) else getattr(risk, "max_lots_per_order", 2)
        if max_lots_per_order < 1:
            raise ValueError("max_lots_per_order must be >=1")

        return data

def load_settings(path: str | Path | None = None) -> Settings:
    # Read the YAML file dictionary
    yaml_data = _load_yaml(Path(path) if path else SETTINGS_YAML)

    # BaseSettings automatically merges kwargs, files, and environment variables
    return Settings(**yaml_data)

def get_settings(path: str | Path | None = None) -> Settings:
    """Return validated settings. Kept as a function for testability."""
    return load_settings(path) if path is not None else settings


settings = load_settings()
