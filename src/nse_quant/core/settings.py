"""Typed global settings with precedence: .env > YAML > defaults."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel,Field,model_validator
from pydantic_settings import BaseSettings,SettingsConfigDict

CONFIG_DIR=Path("config"); SETTINGS_YAML=CONFIG_DIR/"settings.yaml"

class SafetySettings(BaseModel):
    dry_run:bool=True; trading_enabled:bool=False; paper_trading:bool=True
    allowed_strategies:list[str]=Field(default_factory=lambda:["iron_condor_monitor"])

class UniverseSettings(BaseModel):
    underlying:str="NIFTY"; strikes_per_side:int=10

class RuntimeSettings(BaseModel):
    stale_seconds:float=15.0; loop_interval_seconds:int=15

class StorageSettings(BaseModel):
    db_path:Path=Path("data/nse_quant.duckdb"); parquet_dir:Path=Path("data/parquet")
    dashboard_host:str="127.0.0.1"; dashboard_port:int=8050

class AnalyticsSettings(BaseModel):
    risk_free_rate:float=.07; rv_window:int=20; iv_history_limit:int=250
    min_iv_rank:float=40; min_iv_rv_spread:float=.02; max_expected_move_buffer:float=1.15

class IronCondorSettings(BaseModel):
    wing_distance_points:float=200; min_credit:float=20

class StrategySettings(BaseModel):
    iron_condor_monitor:IronCondorSettings=Field(default_factory=IronCondorSettings)

class RiskSettings(BaseModel):
    max_lots_per_order:int=2; max_open_positions:int=3; max_notional_exposure:float=2_000_000
    max_daily_loss:float=25_000; max_portfolio_delta:float=100; max_portfolio_vega:float=5_000
    max_portfolio_gamma:float=.01; max_spread_pct:float=.03; min_oi:int=50_000; min_volume:int=500

class KiteSecrets(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
    kite_api_key:str=""; kite_api_secret:str=""; kite_user_id:str=""; kite_auth_mode:str="manual"

def _load_yaml(path:Path)->dict[str,Any]:
    if not path.exists(): return {}
    value=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value,dict): raise ValueError(f"{path} must contain a mapping")
    return value

class Settings(BaseModel):
    safety:SafetySettings=Field(default_factory=SafetySettings)
    universe:UniverseSettings=Field(default_factory=UniverseSettings)
    runtime:RuntimeSettings=Field(default_factory=RuntimeSettings)
    storage:StorageSettings=Field(default_factory=StorageSettings)
    analytics:AnalyticsSettings=Field(default_factory=AnalyticsSettings)
    strategy:StrategySettings=Field(default_factory=StrategySettings)
    risk:RiskSettings=Field(default_factory=RiskSettings)
    secrets:KiteSecrets=Field(default_factory=KiteSecrets)

    @model_validator(mode="after")
    def validate_safety(self)->"Settings":
        s=self.safety
        if s.trading_enabled and (s.dry_run or s.paper_trading): raise ValueError("Live mode requires DRY_RUN=false and PAPER_TRADING=false")
        if s.trading_enabled: raise ValueError("Live trading is blocked in this milestone")
        if self.runtime.stale_seconds<=0 or self.runtime.loop_interval_seconds<=0: raise ValueError("Runtime timing must be positive")
        if not 0<=self.analytics.min_iv_rank<=100: raise ValueError("min_iv_rank must be 0-100")
        if self.risk.max_lots_per_order<1: raise ValueError("max_lots_per_order must be >=1")
        return self

def load_settings(path:str|Path|None=None)->Settings:
    return Settings.model_validate(_load_yaml(Path(path) if path else SETTINGS_YAML))

settings=load_settings()
