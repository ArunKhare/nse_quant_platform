"""Dynamic NFO chain discovery."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from ..core.constants import CE, PE
from ..core.models import ChainSnapshot, Instrument, OptionQuote, OptionType


def discover_chain(instruments:Iterable[dict[str,Any]],underlying:str,spot:float,expiry:date|None=None,strikes_per_side:int=10):
    rows=[r for r in instruments if r.get("name")==underlying and r.get("instrument_type") in {CE,PE}]
    if not rows: raise ValueError(f"No NFO options for {underlying}")
    def as_date(v:Any)->date: return v if isinstance(v,date) else datetime.strptime(str(v),"%Y-%m-%d").date()
    expiries=sorted({as_date(r["expiry"]) for r in rows if as_date(r["expiry"])>=date.today()})
    expiry=expiry or expiries[0]
    if expiry not in expiries: raise ValueError(f"Expiry unavailable: {expiry}")
    selected=[r for r in rows if as_date(r["expiry"])==expiry]
    strikes=sorted({float(r["strike"]) for r in selected}); atm=min(strikes,key=lambda s:abs(s-spot)); i=strikes.index(atm)
    window=set(strikes[max(0,i-strikes_per_side):i+strikes_per_side+1])
    out=[Instrument(tradingsymbol=r["tradingsymbol"],instrument_token=int(r["instrument_token"]),underlying=underlying,expiry=expiry,strike=float(r["strike"]),option_type=OptionType(r["instrument_type"]),lot_size=int(r["lot_size"])) for r in selected if float(r["strike"]) in window]
    return expiry,out

def build_snapshot(underlying:str,spot:float,expiry:date,instruments:list[Instrument],ticks:dict[int,dict[str,Any]],now:datetime|None=None)->ChainSnapshot:
    now=now or datetime.now(UTC)
    quotes=[]
    for i in instruments:
        t=ticks.get(i.instrument_token,{})
        quotes.append(OptionQuote(instrument_token=i.instrument_token,instrument=i,ltp=t.get("ltp"),bid=t.get("bid"),ask=t.get("ask"),volume=t.get("volume"),oi=t.get("oi"),exchange_ts=t.get("exchange_ts"),trade_ts=t.get("trade_ts"),received_at=t.get("received_at",now)))
    return ChainSnapshot(underlying=underlying,spot=spot,expiry=expiry,quotes=quotes,ts=now)

def discover_chain_multi_expiry(
    instruments: Iterable[dict[str, Any]],
    underlying: str,
    spot: float,
    expiries_requested: int,
    strikes_per_side: int = 10,
) -> list[tuple[date, list[Instrument]]]:
    rows = [
        row
        for row in instruments
        if row.get("name") == underlying
        and row.get("instrument_type") in {CE, PE}
    ]

    if not rows:
        raise ValueError(
            f"No NFO options for {underlying}"
        )

    def as_date(value: Any) -> date:
        if isinstance(value, date):
            return value

        return datetime.strptime(
            str(value), "%Y-%m-%d"
        ).date()

    expiries = sorted(
        {
            as_date(row["expiry"])
            for row in rows
            if as_date(row["expiry"]) >= date.today()
        }
    )

    selected_expiries = expiries[:expiries_requested]

    if len(selected_expiries) < expiries_requested:
        raise ValueError(
             f"Requested {expiries_requested} expiries, "
            f"but only {len(selected_expiries)} are available"
        )

    results: list[tuple[date, list[Instrument]]] = []

    for expiry in selected_expiries:
        expiry_rows = [
            row
            for row in rows
            if as_date(row["expiry"]) == expiry
        ]

        strikes = sorted(
            {
                float(row["strike"])
                for row in expiry_rows
            }
        )

        atm = min(
            strikes,
            key=lambda strike: abs(strike - spot),
        )

        index = strikes.index(atm)

        window = set(
            strikes[
                max(
                    0,
                    index - strikes_per_side,
                ):
                index
                + strikes_per_side
                + 1
            ]
        )

        instruments_for_expiry = [
            Instrument(
                tradingsymbol=row["tradingsymbol"],
                instrument_token=int(
                    row["instrument_token"]
                ),
                underlying=underlying,
                expiry=expiry,
                strike=float(row["strike"]),
                option_type=OptionType(
                    row["instrument_type"]
                ),
                lot_size=int(row["lot_size"]),
            )
            for row in expiry_rows
            if float(row["strike"]) in window
        ]

        results.append(
            (expiry, instruments_for_expiry)
        )

    return results