"""Plotly Dash operations console.

The dashboard is read-only with respect to trading. It can activate the
persistent kill switch, but it cannot place, modify, approve, or cancel orders.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import html

from nse_quant.core.settings import get_settings
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.persistence.duckdb_store import DuckDBStore

settings = get_settings()
store = DuckDBStore()
kill_switch = KillSwitch()


def query_df(sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
    return store.conn.execute(sql, parameters or []).df()


def safety_banner() -> html.Div:
    return html.Div(
        [
            html.Span(f"DRY_RUN={settings.safety.dry_run}"),
            html.Span(f"TRADING_ENABLED={settings.safety.trading_enabled}"),
            html.Span(f"PAPER_TRADING={settings.safety.paper_trading}"),
            html.Span(f"KILL_SWITCH={kill_switch.is_active()}"),
        ],
        style={
            "display": "flex",
            "gap": "24px",
            "fontWeight": "700",
            "marginBottom": "16px",
        },
    )


def iv_smile_figure() -> go.Figure:
    frame = query_df(
        """
        SELECT
            strike,
            option_type,
            AVG(iv) AS iv,
            AVG(ltp) AS ltp
        FROM option_stream
        WHERE underlying = ?
          AND ts = (
              SELECT MAX(ts)
              FROM option_stream
              WHERE underlying = ?
          )
        GROUP BY strike, option_type
        ORDER BY strike
        """,
        [
            settings.universe.underlying,
            settings.universe.underlying,
        ],
    )

    go.Figure()
    figure = go.Figure()

    for option_type, color in (("CE", "#2ca02c"), ("PE", "#d62728")):
        option_frame = frame[frame["option_type"] == option_type]
        figure.add_trace(
            go.Scatter(
                x=option_frame["strike"],
                y=option_frame["iv"],
                mode="lines+markers",
                name=option_type,
                line={"color": color},
            )
        )

    figure.update_layout(xaxis_title="Strike", yaxis_title="Implied volatility")
    return figure