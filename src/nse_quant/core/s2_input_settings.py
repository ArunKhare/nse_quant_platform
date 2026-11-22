"""Typed S2 acquisition settings; no decision or publication authority."""

from typing import Literal

from pydantic import BaseModel, Field


class IndiaVixInputSettings(BaseModel):
    enabled: bool = False
    quote_key: Literal["NSE:INDIA VIX"] = "NSE:INDIA VIX"
    tradingsymbol: Literal["INDIA VIX"] = "INDIA VIX"
    max_age_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
