"""Dash console."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd,plotly.graph_objects as go
from dash import Dash,dcc,html
from core.settings import settings

def load_stream()->pd.DataFrame:
    p=Path("market_data/latest_stream.json")
    if not p.exists(): return pd.DataFrame()
    try: return pd.DataFrame(json.loads(p.read_text()).get("rows",[]))
    except Exception: return pd.DataFrame()

def figure(df:pd.DataFrame)->go.Figure:
    fig=go.Figure()
    if not df.empty and {"strike","iv"}<=set(df.columns):
        for kind,color in (("CE","#2ca02c"),("PE","#d62728")):
            if "kind" in df:
                s=df[(df["kind"]==kind)&df["iv"].notna()]
                if not s.empty: fig.add_scatter(x=s["strike"],y=s["iv"],mode="lines+markers",name=kind,line={"color":color})
    fig.update_layout(title="IV Smile",template="plotly_dark",height=420); return fig

app=Dash(__name__,title="NSE Quant Decision Platform")
app.layout=html.Div([html.H1("NSE Quant Decision Platform"),html.Div([html.Span(f"DRY_RUN={settings.safety.dry_run}"),html.Span(f"TRADING_ENABLED={settings.safety.trading_enabled}"),html.Span(f"PAPER_TRADING={settings.safety.paper_trading}")],style={"display":"flex","gap":"20px","fontWeight":"bold"}),dcc.Graph(id="iv",figure=figure(load_stream())),dcc.Interval(id="r",interval=5000),html.P("Paper trading only. Live execution is disabled.")],style={"margin":"20px","color":"#eee","backgroundColor":"#111"})

@app.callback(__import__("dash").Output("iv","figure"),__import__("dash").Input("r","n_intervals"))
def refresh(_:int): return figure(load_stream())

if __name__=="__main__": app.run(host=settings.storage.dashboard_host,port=settings.storage.dashboard_port,debug=False)
