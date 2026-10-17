"""Plotly Dash operations console.

The dashboard is read-only with respect to trading. It can activate the
persistent kill switch, but it cannot place, modify, approve, or cancel orders.
"""

from __future__ import annotations

import json

from dash import (
    Dash,
    Input,
    Output,
    callback_context,
    dcc,
    html,
)
import plotly.graph_objects as go

from nse_quant.core.settings import get_settings
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.live_snapshot import read_live_snapshot

settings = get_settings()
kill_switch = KillSwitch()
live_snapshot: dict = {}

def load_snapshot() -> dict:
    global live_snapshot
    live_snapshot = read_live_snapshot()
    return live_snapshot


def safety_banner() -> html.Div:
    snapshot = load_snapshot()
    active = snapshot.get("kill_switch_active", False)

    return html.Div(
        [
            html.Span(f"DRY_RUN={settings.safety.dry_run}"),
            html.Span(f"TRADING_ENABLED={settings.safety.trading_enabled}"),
            html.Span(f"PAPER_TRADING={settings.safety.paper_trading}"),
            html.Span(f"KILL_SWITCH={active}"),
            html.Span(f"LOOP={snapshot.get('loop_status', 'idle')}"),
            html.Span(
                f"UPDATED={snapshot.get('updated_at', 'never')}"
            ),
        ],
        style={
            "display": "flex",
            "gap": "24px",
            "fontWeight": "700",
            "marginBottom": "16px",
        },
    )

def iv_smile_figure() -> go.Figure:
    snapshot = load_snapshot()
    features = snapshot.get("features") or {}
    diagnostics = features.get("diagnostics") or {}

    smile_rows = diagnostics.get("iv_smile", [])

    figure = go.Figure()

    for option_type, color in (("CE", "#2ca02c"), ("PE", "#d62728")):
        strikes = []
        ivs = []

        for row in smile_rows:
            if row.get("option_type") == option_type:
                strikes.append(row.get("strike"))
                ivs.append(row.get("iv"))

        figure.add_trace(
            go.Scatter(
                x=strikes,
                y=ivs,
                mode="lines+markers",
                name=option_type,
                line={"color": color},
            )
        )

    figure.update_layout(
        title="Latest IV Smile",
        xaxis_title="Strike",
        yaxis_title="Implied volatility",
        template="plotly_dark",
        height=420,
    )
    return figure


def market_features_table() -> html.Div:
    snapshot = load_snapshot()
    features = snapshot.get("features")

    if not features:
        return html.Div("No feature snapshot available.")

    rows = [
        html.Tr([html.Th(key), html.Td(str(value))])
        for key, value in features.items()
        if key != "diagnostics"
    ]

    return html.Table(
        rows,
        style={"width": "100%", "borderCollapse": "collapse"},
    )


def positions_table() -> html.Div:
    snapshot = load_snapshot()
    positions = snapshot.get("open_positions", [])

    if not positions:
        return html.Div("No open strategy positions.")

    return html.Div(
        [
            html.H3(f"Open strategy positions: {len(positions)}"),
            html.Pre(
                json.dumps(positions, indent=2),
                style={"whiteSpace": "pre-wrap"},
            ),
        ]
    )

app = Dash(
    __name__,
    title="NSE Quant Decision Platform",
    suppress_callback_exceptions=True,
)

app.layout = html.Div(
    [
        html.H1("NSE Quant Decision Platform"),
        safety_banner(),
        html.Button(
            "Activate kill switch",
            id="activate-kill-switch",
            n_clicks=0,
            style={"marginBottom": "20px"},
        ),
        html.Button(
            "Reset kill switch",
            id="reset-kill-switch",
            n_clicks=0,
            style={"marginBottom": "20px", "marginLeft": "12px"},
        ),
        html.Div(id="kill-switch-status"),
        dcc.Graph(id="iv-smile", figure=iv_smile_figure()),
        html.H3("Market features"),
        html.Div(id="market-features", children=market_features_table()),
        html.H3("Open positions"),
        html.Div(id="open-positions", children=positions_table()),
        dcc.Interval(id="refresh", interval=1000),
        html.P(
            "Paper trading only. Live execution is disabled in v0.3.0.",
            style={"marginTop": "24px"},
        ),
    ],
    style={
        "margin": "20px",
        "color": "#eee",
        "backgroundColor": "#111",
        "fontFamily": "Inter, system-ui, sans-serif",
    },
)

@app.callback(
    Output("iv-smile", "figure"),
    Output("market-features", "children"),
    Output("open-positions", "children"),
    Input("refresh", "n_intervals"),
)
def refresh_dashboard(_n_intervals: int) -> tuple[go.Figure, html.Div, html.Div]:
    return (
        iv_smile_figure(),
        market_features_table(),
        positions_table(),
    )

@app.callback(
    Output("kill-switch-status", "children"),
    Input("activate-kill-switch", "n_clicks"),
    Input("reset-kill-switch", "n_clicks"),
    prevent_initial_call=True,
)
def control_kill_switch(
    activate_clicks: int,
    reset_clicks: int,
) -> str:
    triggered = callback_context.triggered

    if not triggered:
        return ""

    trigger_id = triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "activate-kill-switch" and activate_clicks:
        kill_switch.activate("dashboard_manual_kill_switch")
        return "Kill switch activated. New order creation is blocked."

    if trigger_id == "reset-kill-switch" and reset_clicks:
        kill_switch.reset("dashboard_manual_reset")
        return "Kill switch reset."

    return ""

def run() -> None:
    app.run(
        host=settings.storage.dashboard_host,
        port=settings.storage.dashboard_port,
        debug=False,
    )


if __name__ == "__main__":
    run()