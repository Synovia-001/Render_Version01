from __future__ import annotations

import dash
from dash import html, dcc, dash_table, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from flask import has_request_context
from flask_login import current_user
import pandas as pd

from ..data_access import user_can_access_url
from .epos_data_access import load_base, week_dimension, latest_key, qdf, SQL_STOREPROD_ANOM_4W_BY_WEEK, SQL_STOREPROD_WEEKLY_BY_WEEK
from .epos_ml import anomaly_score_storeprod, forecast_next

BASE = "/module/EPOS/"
GRAPH_CONFIG = {"responsive": False, "displayModeBar": True}

def graph(fig, height: int):
    fig.update_layout(height=height, autosize=False, margin=dict(l=10, r=10, t=55, b=10))
    return dcc.Graph(figure=fig, config=GRAPH_CONFIG, style={"height": f"{height}px"})

def money(x):
    try: return f"€{float(x):,.2f}"
    except Exception: return "€0.00"

def num(x):
    try: return f"{int(round(float(x))):,}"
    except Exception: return "0"

def pct(x):
    if x is None: return "n/a"
    try:
        sign = "+" if float(x) >= 0 else ""
        return f"{sign}{float(x):,.1f}%"
    except Exception:
        return "n/a"

def kpi(title: str, value: str, hint: str = ""):
    return dbc.Card(dbc.CardBody([
        html.Div(title, className="kpi-title"),
        html.Div(value, className="kpi-value"),
        html.Div(hint, className="kpi-hint"),
    ]), className="kpi-card")

def _header():
    return dbc.Row([
        dbc.Col(html.Div([
            html.H3("Fusion EPOS", className="mb-0"),
            html.Div(f"Welcome, {getattr(current_user, 'display_name', current_user.get_id())} • Role: {getattr(current_user, 'role', 'User')}", className="subhead"),
        ]), md=10),
        dbc.Col(html.Div([
            html.A("Home", href="/", className="btn btn-outline-primary btn-sm me-2"),
            html.A("Logout", href="/logout", className="btn btn-outline-secondary btn-sm"),
        ], className="text-end"), md=2),
    ], className="align-items-center")

def build_layout():
    if not has_request_context():
        return html.Div()

    if not getattr(current_user, "is_authenticated", False):
        return dbc.Container([dbc.Alert(["Not logged in. ", html.A("Login", href="/login")], color="warning")], className="pt-4")

    user_id = int(current_user.get_id())
    if not user_can_access_url(user_id, "/module/EPOS"):
        return dbc.Container([
            dbc.Alert("You do not have access to Fusion EPOS.", color="danger"),
            html.A("Back to Home", href="/", className="btn btn-outline-primary btn-sm mt-2")
        ], className="pt-4")

    base = load_base(ttl=300)
    wkdim = week_dimension(base.store_weekly)
    default_key = latest_key(base)

    opts = []
    if not wkdim.empty:
        for _, r in wkdim.iterrows():
            key = str(r.get("CalendarKey"))
            sd = r.get("Start_Date")
            year = r.get("Dunnes_Year")
            week = r.get("Dunnes_Week")
            sd_txt = pd.to_datetime(sd).date().isoformat() if pd.notna(sd) else "Unknown"
            if pd.notna(year) and pd.notna(week):
                label = f"{int(year)}-W{int(week):02d} ({sd_txt})"
            else:
                label = f"{key} ({sd_txt})"
            opts.append({"label": label, "value": key})

    controls = dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col([html.Div("Week", className="muted"), dcc.Dropdown(id="epos-week", options=opts, value=default_key, clearable=False)], md=4),
            dbc.Col([html.Div("Anomaly threshold (% dev)", className="muted"),
                     dcc.Slider(id="epos-thresh", min=5, max=80, step=5, value=20)], md=4),
            dbc.Col([html.Div("Actions", className="muted"),
                     dbc.Button("Export Anomalies (CSV)", id="epos-export", color="secondary"),
                     dcc.Download(id="epos-dl")], md=4, className="text-end"),
        ], className="g-3")
    ), className="mt-2")

    tabs = dbc.Tabs([
        dbc.Tab(label="Overview", tab_id="ov"),
        dbc.Tab(label="Anomalies", tab_id="anom"),
        dbc.Tab(label="Explorer", tab_id="exp"),
        dbc.Tab(label="Predictive", tab_id="pred"),
    ], id="epos-tabs", active_tab="ov", className="mt-3")

    return dbc.Container([
        _header(),
        controls,
        tabs,
        html.Div(id="epos-body", className="mt-3")
    ], fluid=True, className="pt-4 pb-5")

def _overview(selected_key: str):
    base = load_base(ttl=300)
    sw = base.store_weekly.copy()
    sw["CalendarKey"] = sw["CalendarKey"].astype(str)

    cur = sw[sw["CalendarKey"] == str(selected_key)].copy()
    if cur.empty:
        return dbc.Alert("No rows for selected week.", color="info")

    total_units = float(cur.get("Units", 0).sum())
    total_value = float(cur.get("Value", 0).sum())

    tw = sw.dropna(subset=["Start_Date"]).groupby(["CalendarKey","Start_Date"], as_index=False).agg(Units=("Units","sum"), Value=("Value","sum")).sort_values("Start_Date")
    cur_row = tw[tw["CalendarKey"] == str(selected_key)]
    cur_row = cur_row.iloc[0] if not cur_row.empty else tw.iloc[-1]
    idx = tw.index[tw["CalendarKey"] == str(cur_row["CalendarKey"])][0]
    prev_row = tw.iloc[idx-1] if idx > 0 else cur_row
    wow_units = ((total_units - float(prev_row["Units"])) / float(prev_row["Units"]) * 100.0) if float(prev_row["Units"]) else None
    wow_value = ((total_value - float(prev_row["Value"])) / float(prev_row["Value"]) * 100.0) if float(prev_row["Value"]) else None

    top = cur.groupby("Store_Name", as_index=False).agg(Units=("Units","sum")).sort_values("Units", ascending=False).head(15)
    fig_top = go.Figure(go.Bar(x=top["Units"], y=top["Store_Name"], orientation="h"))
    fig_top.update_layout(title="Top Stores (Units)")

    trend = tw.tail(26)
    fig_tr = go.Figure(go.Scatter(x=trend["Start_Date"], y=trend["Units"], mode="lines+markers"))
    fig_tr.update_layout(title="Units Trend (26 weeks)")

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("Units (week)", num(total_units), f"WoW: {pct(wow_units)}"), md=3),
            dbc.Col(kpi("Value (week)", money(total_value), f"WoW: {pct(wow_value)}"), md=3),
            dbc.Col(kpi("Stores active", num(cur["Store_Name"].nunique()), "Stores with sales"), md=3),
            dbc.Col(kpi("Rows", num(len(cur)), "Store-week rows"), md=3),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_tr, 360), md=6), dbc.Col(graph(fig_top, 520), md=6)], className="g-3 mt-2"),
    ], fluid=True, className="p-0")

def _anomalies(selected_key: str, thresh: int):
    df = qdf(SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(selected_key)], ttl=120)
    if df.empty:
        return dbc.Alert("No anomalies for this week.", color="info")

    for c in ["Units_DevPct_4W","Base_Units_4W","Units","Value","Base_Value_4W"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    flag = "IsUnitsAnomaly_4W" if "IsUnitsAnomaly_4W" in df.columns else None
    if flag:
        f = df[(df[flag].astype(int) == 1) | (df["Units_DevPct_4W"].abs() >= float(thresh))].copy()
    else:
        f = df[df["Units_DevPct_4W"].abs() >= float(thresh)].copy()

    if f.empty:
        return dbc.Alert(f"No anomalies above ±{thresh}%.", color="info")

    f = anomaly_score_storeprod(f)
    f["Label"] = f["Store_Name"].astype(str).str.slice(0,20) + " | " + f["Dynamics_Code"].astype(str)
    movers = f.sort_values(f["Units_DevPct_4W"].abs(), ascending=False).head(20).sort_values("Units_DevPct_4W")
    fig = go.Figure(go.Bar(x=movers["Units_DevPct_4W"], y=movers["Label"], orientation="h"))
    fig.update_layout(title="Top 20 movers vs 4W baseline (Units %)")
    fig.update_yaxes(categoryorder="total ascending")

    show_cols = [c for c in ["Store_Name","Dynamics_Code","Product_Description","Units","Base_Units_4W","Units_DevPct_4W","Value","Base_Value_4W","ML_AnomalyScore"] if c in f.columns]
    tf = f[show_cols].copy()
    if "Units_DevPct_4W" in tf.columns: tf["Units_DevPct_4W"] = tf["Units_DevPct_4W"].round(1)
    if "ML_AnomalyScore" in tf.columns: tf["ML_AnomalyScore"] = tf["ML_AnomalyScore"].round(2)

    table = dash_table.DataTable(
        columns=[{"name": c.replace("_"," "), "id": c} for c in tf.columns],
        data=tf.sort_values("ML_AnomalyScore", ascending=False).head(300).to_dict("records"),
        page_size=20,
        filter_action="native",
        sort_action="native",
        style_table={"overflowX":"auto"},
        style_cell={"fontFamily":"Segoe UI, Arial","fontSize":13,"padding":"8px","whiteSpace":"normal","height":"auto"},
        style_header={"fontWeight":"700"},
    )

    impact = (tf["Base_Value_4W"] - tf["Value"]).clip(lower=0).sum() if "Base_Value_4W" in tf.columns and "Value" in tf.columns else 0.0

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("Rows flagged", num(len(tf)), f"Threshold: ±{thresh}%"), md=3),
            dbc.Col(kpi("Potential impact", money(impact), "Base - Actual (positive only)"), md=3),
            dbc.Col(kpi("Max ML score", f"{float(tf['ML_AnomalyScore'].max()):.2f}" if "ML_AnomalyScore" in tf.columns else "n/a", "IsolationForest"), md=3),
            dbc.Col(kpi("Avg dev %", f"{float(tf['Units_DevPct_4W'].abs().mean()):.1f}%" if "Units_DevPct_4W" in tf.columns else "n/a", "Abs deviation"), md=3),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig, 520), md=6), dbc.Col(dbc.Card(dbc.CardBody([html.Div("Anomaly Table", className="section-title"), table])), md=6)], className="g-3 mt-2"),
        dbc.Alert("Anomalies are loaded from CUR.vw_StoreProductAnomalies_4W for the selected week. Use filters to drill in.", color="secondary", className="mt-3")
    ], fluid=True, className="p-0")

def _explorer(selected_key: str):
    df = qdf(SQL_STOREPROD_WEEKLY_BY_WEEK, [str(selected_key)], ttl=120)
    if df.empty:
        return dbc.Alert("No Store×Product weekly rows for this week.", color="info")
    cols = [c for c in ["Store_Name","Dynamics_Code","Product_Description","Units","Value","CalendarKey","Start_Date"] if c in df.columns]
    df = df[cols].copy()
    if "Start_Date" in df.columns:
        df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.head(2000)
    table = dash_table.DataTable(
        columns=[{"name": c.replace("_"," "), "id": c} for c in df.columns],
        data=df.to_dict("records"),
        page_size=20,
        filter_action="native",
        sort_action="native",
        style_table={"overflowX":"auto"},
        style_cell={"fontFamily":"Segoe UI, Arial","fontSize":13,"padding":"8px"},
        style_header={"fontWeight":"700"},
    )
    return dbc.Card(dbc.CardBody([html.Div("Store×Product Weekly (sample)", className="section-title"), table]))

def _predictive(selected_key: str):
    base = load_base(ttl=300)
    sw = base.store_weekly.copy()
    tw = sw.dropna(subset=["Start_Date"]).groupby(["CalendarKey","Start_Date"], as_index=False).agg(Units=("Units","sum"), Value=("Value","sum")).sort_values("Start_Date")
    if len(tw) < 12:
        return dbc.Alert("Need at least 12 weeks of history for forecasting.", color="info")
    fu = forecast_next(tw, "Units", "Start_Date")
    fv = forecast_next(tw, "Value", "Start_Date")
    hist = tw.tail(52).copy()

    fig_u = go.Figure()
    fig_u.add_trace(go.Scatter(x=hist["Start_Date"], y=hist["Units"], mode="lines+markers", name="Actual"))
    if fu is not None:
        next_date = hist["Start_Date"].iloc[-1] + pd.Timedelta(days=7)
        fig_u.add_trace(go.Scatter(x=[next_date], y=[fu], mode="markers", marker={"size": 14}, name="Forecast"))
    fig_u.update_layout(title="Forecast next week Units (seasonal ridge)")

    fig_v = go.Figure()
    fig_v.add_trace(go.Scatter(x=hist["Start_Date"], y=hist["Value"], mode="lines+markers", name="Actual"))
    if fv is not None:
        next_date = hist["Start_Date"].iloc[-1] + pd.Timedelta(days=7)
        fig_v.add_trace(go.Scatter(x=[next_date], y=[fv], mode="markers", marker={"size": 14}, name="Forecast"))
    fig_v.update_layout(title="Forecast next week Value (seasonal ridge)")

    return dbc.Container([
        dbc.Alert("Predictive analytics: lightweight seasonal regression forecast. Next: per-store/product forecasting + confidence bands.", color="primary"),
        dbc.Row([dbc.Col(kpi("Forecast Units (next week)", num(fu) if fu is not None else "n/a", "Model: ridge"), md=6),
                 dbc.Col(kpi("Forecast Value (next week)", money(fv) if fv is not None else "n/a", "Model: ridge"), md=6)], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_u, 360), md=6), dbc.Col(graph(fig_v, 360), md=6)], className="g-3 mt-2")
    ], fluid=True, className="p-0")

def create_epos_dash_app(server):
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname=BASE,
        external_stylesheets=[dbc.themes.FLATLY],
        title="Fusion EPOS",
        suppress_callback_exceptions=True,
    )
    app.layout = build_layout

    @app.callback(
        Output("epos-body", "children"),
        Input("epos-tabs", "active_tab"),
        Input("epos-week", "value"),
        Input("epos-thresh", "value"),
    )
    def render_body(tab, week, thresh):
        if not week:
            return dbc.Alert("Select a week.", color="info")
        if tab == "ov":
            return _overview(str(week))
        if tab == "anom":
            return _anomalies(str(week), int(thresh or 20))
        if tab == "exp":
            return _explorer(str(week))
        if tab == "pred":
            return _predictive(str(week))
        return dbc.Alert("Unknown tab.", color="warning")

    @app.callback(
        Output("epos-dl", "data"),
        Input("epos-export", "n_clicks"),
        State("epos-week", "value"),
        State("epos-thresh", "value"),
        prevent_initial_call=True,
    )
    def export_anoms(n, week, thresh):
        if not n:
            return no_update
        df = qdf(SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(week)], ttl=0)
        if df.empty:
            return no_update
        if "Units_DevPct_4W" in df.columns:
            df["Units_DevPct_4W"] = pd.to_numeric(df["Units_DevPct_4W"], errors="coerce").fillna(0.0)
            df = df[df["Units_DevPct_4W"].abs() >= float(thresh or 20)].copy()
        return dcc.send_data_frame(df.to_csv, filename=f"epos_anomalies_week_{week}.csv", index=False, encoding="utf-8-sig")

    return app
