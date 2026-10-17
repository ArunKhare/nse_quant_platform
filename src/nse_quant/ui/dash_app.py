"""Readable Plotly Dash operations console.

The dashboard is read-only with respect to trading. It can activate or reset
the persistent kill switch, but it cannot place, modify, approve, or cancel
orders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import plotly.graph_objects as go
from dash import Dash, Input, Output, callback_context, dcc, html

from nse_quant.core.settings import get_settings
from nse_quant.ops.kill_switch import KillSwitch
from nse_quant.ops.live_snapshot import read_live_snapshot

settings = get_settings()
kill_switch = KillSwitch()

APP_BACKGROUND = "#0b1220"
CARD_BACKGROUND = "#111a2b"
CARD_BORDER = "#223047"
TEXT_PRIMARY = "#e6edf7"
TEXT_MUTED = "#94a3b8"
ACCENT = "#38bdf8"
GREEN = "#22c55e"
AMBER = "#f59e0b"
RED = "#ef4444"


def format_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"

    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def format_time(value: Any) -> str:
    if not value:
        return "Never"

    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%d %b %Y, %H:%M:%S %Z")
    except ValueError:
        return str(value)


def status_pill(label: str, value: str, color: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "fontSize": "11px",
                    "letterSpacing": "0.08em",
                    "textTransform": "uppercase",
                    "color": TEXT_MUTED,
                    "marginBottom": "6px",
                },
            ),
            html.Div(
                value,
                style={
                    "fontSize": "18px",
                    "fontWeight": "700",
                    "color": color,
                },
            ),
        ],
        style={
            "backgroundColor": CARD_BACKGROUND,
            "border": f"1px solid {CARD_BORDER}",
            "borderRadius": "12px",
            "padding": "16px 18px",
            "minWidth": "170px",
            "flex": "1",
        },
    )


def safety_banner(snapshot: dict[str, Any]) -> html.Div:
    kill_switch_active = bool(snapshot.get("kill_switch_active", False))
    loop_status = snapshot.get("loop_status", "idle")
    quality = snapshot.get("data_quality", {})
    trading_color = GREEN if settings.safety.paper_trading else RED
    kill_color = RED if kill_switch_active else GREEN
    loop_color = (
        GREEN
        if loop_status in {"paper_filled", "dry_run"}
        else AMBER
        if loop_status in {"no_proposal", "risk_rejected", "idle"}
        else RED
    )

    return html.Div(
        [
            status_pill(
                "Execution mode",
                "PAPER ONLY",
                trading_color,
            ),
            status_pill(
                "Live trading",
                "BLOCKED",
                RED,
            ),
            status_pill(
                "Kill switch",
                "ACTIVE" if kill_switch_active else "CLEAR",
                kill_color,
            ),
            status_pill(
                "Loop status",
                str(loop_status).upper(),
                loop_color,
            ),
            status_pill(
                "Data quality",
                "OK" if quality.get("is_usable") else "DEGRADED",
                GREEN if quality.get("is_usable") else AMBER,
            ),
            status_pill(
                "Last update",
                format_time(snapshot.get("updated_at")),
                TEXT_PRIMARY,
            ),
        ],
        style={
            "display": "flex",
            "gap": "14px",
            "flexWrap": "wrap",
            "marginBottom": "22px",
        },
    )

def data_quality_section(snapshot: dict[str, Any]) -> html.Div:
    quality = snapshot.get("data_quality", {})

    issues = quality.get("issues", [])
    warnings = quality.get("warnings", [])

    if not issues and not warnings:
        return html.Div("Market data quality is healthy.")

    return html.Div(
        [
            html.H3("Data-quality issues"),
            html.Ul([html.Li(issue) for issue in issues]),
            html.H3("Warnings"),
            html.Ul([html.Li(warning) for warning in warnings]),
        ]
    )

def metric_card(
    label: str,
    value: Any,
    suffix: str = "",
    decimals: int = 2,
    color: str | None = None,
) -> html.Div:
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "fontSize": "11px",
                    "letterSpacing": "0.08em",
                    "textTransform": "uppercase",
                    "color": TEXT_MUTED,
                    "marginBottom": "6px",
                },
            ),
            html.Div(
                [
                    html.Span(
                        format_number(value, decimals),
                        style={
                            "fontSize": "22px",
                            "fontWeight": "700",
                            "fontFamily": "Consolas, monospace",
                            "color": color or TEXT_PRIMARY,
                        },
                    ),
                    html.Span(
                        f" {suffix}",
                        style={
                            "fontSize": "13px",
                            "color": TEXT_MUTED,
                        },
                    ),
                ]
            ),
        ],
        style={
            "backgroundColor": CARD_BACKGROUND,
            "border": f"1px solid {CARD_BORDER}",
            "borderRadius": "12px",
            "padding": "16px 18px",
            "minWidth": "155px",
            "flex": "1",
        },
    )


def market_metric_cards(snapshot: dict[str, Any]) -> html.Div:
    features = snapshot.get("features") or {}

    iv_rank = features.get("iv_rank")
    iv_rank_color = (
        GREEN
        if iv_rank is not None and iv_rank >= settings.analytics.min_iv_rank
        else AMBER
    )

    expected_move = features.get("expected_move_points")

    return html.Div(
        [
            metric_card(
                "NIFTY spot",
                features.get("spot"),
                decimals=2,
            ),
            metric_card(
                "ATM IV",
                features.get("atm_iv"),
                suffix="%",
                decimals=2,
            ),
            metric_card(
                "IV rank",
                iv_rank,
                suffix="%",
                decimals=1,
                color=iv_rank_color,
            ),
            metric_card(
                "IV − RV",
                features.get("iv_rv_spread"),
                decimals=3,
            ),
            metric_card(
                "PCR",
                features.get("pcr"),
                decimals=2,
            ),
            metric_card(
                "Expected move",
                expected_move,
                suffix="pts",
                decimals=1,
                color=ACCENT,
            ),
            metric_card(
                "Regime",
                str(features.get("regime", "UNKNOWN")).replace("_", " "),
                decimals=0,
            ),
        ],
        style={
            "display": "flex",
            "gap": "14px",
            "flexWrap": "wrap",
            "marginBottom": "22px",
        },
    )


def section_card(
    title: str,
    child: Any,
    subtitle: str | None = None,
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H2(
                        title,
                        style={
                            "fontSize": "18px",
                            "margin": "0",
                            "color": TEXT_PRIMARY,
                        },
                    ),
                    html.Div(
                        subtitle or "",
                        style={
                            "fontSize": "13px",
                            "color": TEXT_MUTED,
                            "marginTop": "4px",
                        },
                    ),
                ],
                style={"marginBottom": "16px"},
            ),
            child,
        ],
        style={
            "backgroundColor": CARD_BACKGROUND,
            "border": f"1px solid {CARD_BORDER}",
            "borderRadius": "14px",
            "padding": "20px",
            "marginBottom": "20px",
        },
    )


def data_table(
    columns: list[str],
    rows: list[list[Any]],
) -> html.Table:
    header = html.Tr(
        [
            html.Th(
                column,
                style={
                    "textAlign": "left",
                    "padding": "10px 12px",
                    "color": TEXT_MUTED,
                    "fontSize": "12px",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.06em",
                    "borderBottom": f"1px solid {CARD_BORDER}",
                },
            )
            for column in columns
        ]
    )

    body = [
        html.Tr(
            [
                html.Td(
                    format_number(cell) if isinstance(cell, (int, float)) else str(cell),
                    style={
                        "padding": "10px 12px",
                        "borderBottom": f"1px solid {CARD_BORDER}",
                        "fontFamily": (
                            "Consolas, monospace"
                            if isinstance(cell, (int, float))
                            else "inherit"
                        ),
                        "textAlign": (
                            "right"
                            if isinstance(cell, (int, float))
                            else "left"
                        ),
                        "color": TEXT_PRIMARY,
                    },
                )
                for cell in row
            ]
        )
        for row in rows
    ]

    return html.Table(
        [header, *body],
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "fontSize": "14px",
        },
    )


def empty_state(message: str) -> html.Div:
    return html.Div(
        message,
        style={
            "color": TEXT_MUTED,
            "backgroundColor": "#0f172a",
            "border": f"1px dashed {CARD_BORDER}",
            "borderRadius": "10px",
            "padding": "22px",
            "textAlign": "center",
        },
    )


def market_features_table(snapshot: dict[str, Any]) -> html.Div:
    features = snapshot.get("features")

    if not features:
        return empty_state("No market feature snapshot available yet.")

    rows = [
        ["Spot", format_number(features.get("spot"))],
        ["ATM IV", format_number(features.get("atm_iv"), 2)],
        ["IV rank", format_number(features.get("iv_rank"), 1)],
        ["IV percentile", format_number(features.get("iv_percentile"), 1)],
        ["Realized volatility", format_number(features.get("realized_vol"), 2)],
        ["IV − RV spread", format_number(features.get("iv_rv_spread"), 3)],
        ["PCR", format_number(features.get("pcr"), 2)],
        ["Max pain", format_number(features.get("max_pain"), 0)],
        ["Expected move", format_number(features.get("expected_move_points"), 1)],
        ["Regime", str(features.get("regime", "UNKNOWN")).replace("_", " ")],
    ]

    return data_table(["Metric", "Value"], rows)


def iv_smile_figure(snapshot: dict[str, Any]) -> go.Figure:
    features = snapshot.get("features") or {}
    diagnostics = features.get("diagnostics") or {}
    smile_rows = diagnostics.get("iv_smile", [])

    figure = go.Figure()

    for option_type, color in (("CE", GREEN), ("PE", RED)):
        selected = [
            row
            for row in smile_rows
            if row.get("option_type") == option_type
        ]

        figure.add_trace(
            go.Scatter(
                x=[row.get("strike") for row in selected],
                y=[row.get("iv") for row in selected],
                mode="lines+markers",
                name=option_type,
                line={"color": color, "width": 2},
                marker={"size": 6},
            )
        )

    figure.update_layout(
        title={
            "text": "IV Smile",
            "font": {"color": TEXT_PRIMARY},
        },
        template="plotly_dark",
        height=380,
        margin={"l": 50, "r": 25, "t": 55, "b": 45},
        paper_bgcolor=CARD_BACKGROUND,
        plot_bgcolor=CARD_BACKGROUND,
        font={"color": TEXT_PRIMARY},
        xaxis={
            "title": {"text": "Strike"},
            "gridcolor": CARD_BORDER,
        },
        yaxis={
            "title": {"text": "Implied volatility"},
            "gridcolor": CARD_BORDER,
        },
        legend={
            "orientation": "h",
            "y": -0.2,
        },
    )
    return figure


def positions_table(snapshot: dict[str, Any]) -> html.Div:
    positions = snapshot.get("open_positions", [])

    if not positions:
        return empty_state("No open strategy positions.")

    rows = []

    for position in positions:
        rows.append(
            [
                position.get("strategy", "—"),
                position.get("underlying", "—"),
                format_number(position.get("entry_price")),
                format_number(position.get("current_price")),
                format_number(position.get("unrealized_pnl")),
                position.get("status", "—"),
            ]
        )

    return data_table(
        [
            "Strategy",
            "Underlying",
            "Entry",
            "Mark",
            "Unrealized P&L",
            "Status",
        ],
        rows,
    )


app = Dash(
    __name__,
    title="NSE Quant Decision Platform",
    suppress_callback_exceptions=True,
)

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.H1(
                            "NSE Quant Decision Platform",
                            style={
                                "margin": "0",
                                "fontSize": "24px",
                                "color": TEXT_PRIMARY,
                            },
                        ),
                        html.Div(
                            "NIFTY options paper-trading decision console",
                            style={
                                "color": TEXT_MUTED,
                                "fontSize": "14px",
                                "marginTop": "4px",
                            },
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Button(
                            "Activate kill switch",
                            id="activate-kill-switch",
                            n_clicks=0,
                            style={
                                "backgroundColor": RED,
                                "color": "white",
                                "border": "none",
                                "borderRadius": "8px",
                                "padding": "10px 16px",
                                "fontWeight": "600",
                                "cursor": "pointer",
                            },
                        ),
                        html.Button(
                            "Reset kill switch",
                            id="reset-kill-switch",
                            n_clicks=0,
                            style={
                                "backgroundColor": CARD_BACKGROUND,
                                "color": TEXT_PRIMARY,
                                "border": f"1px solid {CARD_BORDER}",
                                "borderRadius": "8px",
                                "padding": "10px 16px",
                                "fontWeight": "600",
                                "cursor": "pointer",
                                "marginLeft": "10px",
                            },
                        ),
                    ]
                ),
            ],
            style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "flexWrap": "wrap",
                "gap": "16px",
                "marginBottom": "22px",
            },
        ),
        html.Div(id="safety-banner"),
        html.Div(id="market-metrics"),
        html.Div(id="data-quality"),
        section_card(
            "IV smile",
            dcc.Graph(
                id="iv-smile",
                config={"displayModeBar": False},
            ),
            "Latest implied-volatility smile from the active chain snapshot",
        ),
        section_card(
            "Market features",
            html.Div(id="market-features"),
        ),
        section_card(
            "Open strategy positions",
            html.Div(id="open-positions"),
            "Each iron condor is a logical group of independent option legs",
        ),
        html.Div(
            "Paper trading only. Live execution is structurally disabled in v0.3.0.",
            style={
                "color": TEXT_MUTED,
                "textAlign": "center",
                "marginTop": "20px",
                "fontSize": "13px",
            },
        ),
        dcc.Interval(id="refresh", interval=1000),
    ],
    style={
        "maxWidth": "1280px",
        "margin": "0 auto",
        "padding": "28px 22px",
        "backgroundColor": APP_BACKGROUND,
        "color": TEXT_PRIMARY,
        "fontFamily": "Inter, Segoe UI, system-ui, sans-serif",
        "minHeight": "100vh",
    },
)


@app.callback(
    Output("safety-banner", "children"),
    Output("market-metrics", "children"),
    Output("data-quality", "children"),
    Output("iv-smile", "figure"),
    Output("market-features", "children"),
    Output("open-positions", "children"),
    Input("refresh", "n_intervals"),
)
def refresh_dashboard(_n_intervals: int):
    snapshot = read_live_snapshot()

    return (
        safety_banner(snapshot),
        market_metric_cards(snapshot),
        data_quality_section(snapshot),
        iv_smile_figure(snapshot),
        market_features_table(snapshot),
        positions_table(snapshot),
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