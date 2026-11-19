"""Run a deterministic research-only vectorbt backtest from an aligned CSV.

Required CSV columns: ts,price,entry,exit. The entry and exit columns must be
boolean values. This CLI does not place orders or authorize trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nse_quant.research.backtest.vectorbt_adapter import VectorbtAdapterSettings
from nse_quant.research.backtest.vectorbt_backtest import (
    VectorbtBacktestRequest,
    run_vectorbt_backtest,
)
from nse_quant.research.backtest.vectorbt_manifest import build_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices-csv", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--fees", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    args = parser.parse_args()

    frame = pd.read_csv(args.prices_csv)
    required = {"ts", "price", "entry", "exit"}
    missing = required.difference(frame.columns)
    if missing:
        raise SystemExit(f"Missing CSV columns: {sorted(missing)}")

    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").set_index("ts")
    prices = frame["price"].astype(float)
    entries = frame["entry"].astype(bool)
    exits = frame["exit"].astype(bool)

    request = VectorbtBacktestRequest(
        strategy="iron_condor_monitor",
        underlying="NIFTY",
        prices=prices,
        entries=entries,
        exits=exits,
        settings=VectorbtAdapterSettings(
            initial_capital=args.initial_capital,
            fees=args.fees,
            slippage=args.slippage,
        ),
    )

    result = run_vectorbt_backtest(request)
    input_hash = (
        __import__("hashlib")
        .sha256(
            __import__("json")
            .dumps(
                frame.reset_index().to_dict(orient="records"),
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            .encode()
        )
        .hexdigest()
    )
    manifest = build_manifest(
        strategy=request.strategy,
        underlying=request.underlying,
        input_hash=input_hash,
        parameters={
            "initial_capital": args.initial_capital,
            "fees": args.fees,
            "slippage": args.slippage,
        },
        result=result,
    )

    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"Vectorbt backtest complete: {output}")


if __name__ == "__main__":
    main()
