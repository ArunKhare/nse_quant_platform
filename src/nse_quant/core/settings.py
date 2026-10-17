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
    enforce_market_hours: bool = True

class StorageSettings(BaseModel):
    db_path: Path = Path("data/nse_quant.duckdb")
    parquet_dir: Path = Path("data/parquet")
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8050

class AnalyticsSettings(BaseModel):
    risk_free_rate: float = .07
    rv_window: int = 20
    iv_history_limit: int = 250
    min_iv_history_observations: int = 30
    min_iv_rank: float = 40
    min_iv_rv_spread: float = .02
    max_expected_move_buffer: float = 1.15

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
    notifier: NotifierSettings = Field(default_factory=NotifierSettings)
    secrets: KiteSecrets = Field(default_factory=KiteSecrets)

    # @model_validator(mode="after")
    # def validate_safety(self) -> Settings:
    #     s = self.safety
    #     if s.trading_enabled and (s.dry_run or s.paper_trading):
    #         raise ValueError("Live mode requires DRY_RUN=false and PAPER_TRADING=false")
    #     if s.trading_enabled:
    #         raise ValueError("Live trading is blocked in this milestone")
    #     if self.runtime.stale_seconds <= 0 or self.runtime.loop_interval_seconds <= 0:
    #         raise ValueError("Runtime timing must be positive")
    #     if not 0 <= self.analytics.min_iv_rank <= 100:
    #         raise ValueError("min_iv_rank must be 0-100")
    #     if self.risk.max_lots_per_order < 1:
    #         raise ValueError("max_lots_per_order must be >=1")
        # return self

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
