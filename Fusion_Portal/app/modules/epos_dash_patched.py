from __future__ import annotations

import dash
from dash import html, dcc, dash_table, Input, Output, State, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from flask import has_request_context
from flask_login import current_user
import pandas as pd
import json
import math
from datetime import datetime
from pathlib import Path

from ..data_access import user_can_access_url
from .epos_data_access import (
    load_base,
    calendar_dimension,
    load_pack_sizes,
    week_dimension,
    latest_key,
    qdf,
    SQL_STOREPROD_ANOM_4W_BY_WEEK,
    SQL_STOREPROD_WEEKLY_BY_WEEK,
    SQL_STOREPROD_WEEKLY_BY_WEEK_STORE,
    SQL_STOREPROD_WEEKLY_BY_WEEK_PRODUCT,
    SQL_STOREPROD_HISTORY,
)
from .epos_ml import anomaly_score_storeprod, forecast_next, holt_winters_forecast, detect_change_points

BASE = "/module/EPOS/"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
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



def kpi_action(title, value, hint, button_id, button_text="Review"):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="kpi-title"),
                html.Div(value, className="kpi-value"),
                html.Div(hint, className="kpi-hint"),
                dbc.Button(button_text, id=button_id, color="primary", size="sm", className="mt-2"),
            ]
        ),
        className="kpi-card",
    )

def build_layout(asset_url):
    if not has_request_context():
        return html.Div()

    if not getattr(current_user, "is_authenticated", False):
        return dbc.Container(
            [dbc.Alert(["Not logged in. ", html.A("Login", href="/login")], color="warning")],
            className="pt-4",
        )

    user_id = int(current_user.get_id())
    if not user_can_access_url(user_id, "/module/EPOS"):
        return dbc.Container(
            [
                dbc.Alert("You do not have access to Fusion EPOS.", color="danger"),
                html.A("Back to Home", href="/", className="btn btn-outline-primary btn-sm mt-2"),
            ],
            className="pt-4",
        )

    # Load cached base datasets. If EPOS_DB isn't configured or the DB is unavailable,
    # fail gracefully instead of crashing Dash during layout validation.
    base = None
    cal = pd.DataFrame()
    try:
        base = load_base(ttl=300)

        # Use CFG.Calenders so the week labels always match the retail calendar (incl. year boundaries)
        cal = calendar_dimension(ttl=3600)
    except Exception as e:
        return dbc.Container(
            [
                dbc.Alert(
                    [
                        html.Div("Fusion EPOS could not load required data.", className="fw-bold"),
                        html.Div(str(e), className="small text-muted"),
                        html.Div(
                            "Check Render env vars (EPOS_DB) and confirm the database contains CFG.Calenders and the EPOS views.",
                            className="small",
                        ),
                    ],
                    color="danger",
                ),
                html.A("Back to Home", href="/", className="btn btn-outline-primary btn-sm mt-2"),
            ],
            className="pt-4",
        )

    # Filter the calendar to only keys present in the facts (prevents showing future weeks with no data).
    if (
        (not cal.empty)
        and (not base.store_weekly.empty)
        and ("CalendarKey" in base.store_weekly.columns)
        and ("CalendarKey" in cal.columns)
    ):
        keys = set(base.store_weekly["CalendarKey"].astype(str).unique())
        wkdim = cal[cal["CalendarKey"].astype(str).isin(keys)].copy()
    elif not cal.empty:
        wkdim = cal.copy()
    else:
        wkdim = week_dimension(base.store_weekly)

    default_key = latest_key(base)
    if (default_key is None or str(default_key).strip() == "") and (not wkdim.empty):
        default_key = str(wkdim.iloc[-1].get("CalendarKey"))

    # Week dropdown
    opts = []
    if not wkdim.empty:
        for _, r in wkdim.iterrows():
            key = str(r.get("CalendarKey"))
            sd = pd.to_datetime(r.get("Start_Date")).date().isoformat() if pd.notnull(r.get("Start_Date")) else ""
            ed = ""
            if "End_Date" in wkdim.columns:
                ed = pd.to_datetime(r.get("End_Date")).date().isoformat() if pd.notnull(r.get("End_Date")) else ""

            dy = r.get("Dunnes_Year")
            dw = r.get("Dunnes_Week")
            if pd.notnull(dy) and pd.notnull(dw):
                try:
                    y = int(dy)
                    w = int(dw)
                    if ed:
                        label = f"{y}-W{w:02d} ({sd} → {ed})"
                    else:
                        label = f"{y}-W{w:02d} ({sd})"
                except Exception:
                    label = f"{key} ({sd} → {ed})" if ed else f"{key} ({sd})"
            else:
                label = f"{key} ({sd} → {ed})" if ed else f"{key} ({sd})"

            opts.append({"label": label, "value": key})
# Store list
    stores = []
    if "Store_Name" in base.store_weekly.columns:
        stores = sorted(base.store_weekly["Store_Name"].dropna().astype(str).unique().tolist())

    # Product list (code + description if available)
    prods = []
    if "Dynamics_Code" in base.product_weekly.columns:
        tmp = base.product_weekly.dropna(subset=["Dynamics_Code"]).copy()
        tmp["Dynamics_Code"] = tmp["Dynamics_Code"].astype(str)
        if "Product_Description" in tmp.columns:
            tmp["label"] = tmp["Dynamics_Code"] + " — " + tmp["Product_Description"].astype(str)
        else:
            tmp["label"] = tmp["Dynamics_Code"]
        tmp = tmp.drop_duplicates(subset=["Dynamics_Code"])
        prods = [{"label": r["label"], "value": r["Dynamics_Code"]} for _, r in tmp.iterrows()]

    # Branding header + side + footer
    header = html.Div([
        html.Div([
            html.Img(src=asset_url("FusionLogo.jpg"), className="brand-fusion-logo"),
            html.Div([
                html.Div("Fusion EPOS", className="brand-title"),
                html.Div(
                    f"Welcome, {getattr(current_user, 'display_name', current_user.get_id())} • Role: {getattr(current_user, 'role', 'User')}",
                    className="subhead"
                ),
            ])
        ], className="brand-left"),
        html.Div([
            html.A("Home", href="/", className="btn btn-outline-primary btn-sm me-2"),
            html.A("Logout", href="/logout", className="btn btn-outline-secondary btn-sm"),
        ])
    ], className="brand-header")

    side = html.Div(
        html.Img(src=asset_url("RunningBunny.jpg"), className="brand-duracell-bunny"),
        className="brand-side"
    )

    footer = html.Div(
        html.Img(src=asset_url("SynoviaLogoHor.jpg"), className="brand-synovia-logo"),
        className="brand-footer"
    )

    controls = dbc.Card(dbc.CardBody(
        dbc.Row([
            dbc.Col([html.Div("Week", className="muted"),
                     dcc.Dropdown(id="epos-week", options=opts, value=default_key, clearable=False)], md=3),

            dbc.Col([html.Div("Store", className="muted"),
                     dcc.Dropdown(id="epos-store", options=[{"label": s, "value": s} for s in stores], value=None, placeholder="(optional) choose store")], md=3),

            dbc.Col([html.Div("Product", className="muted"),
                     dcc.Dropdown(id="epos-product", options=prods, value=None, placeholder="(optional) choose product")], md=3),

            dbc.Col([html.Div("Threshold (% dev)", className="muted"),
                     dcc.Slider(id="epos-thresh", min=5, max=80, step=5, value=20)], md=3),
        ], className="g-3")
    ), className="mt-2")

    actions = dbc.Row([
        dbc.Col(html.Div([
            dbc.Button("Export Anomalies (CSV)", id="epos-export", color="secondary", className="me-2"),
            dbc.Button("Clear cache", id="epos-clear-cache", color="outline-secondary"),
            dcc.Download(id="epos-dl")
        ], className="text-end"), md=12)
    ], className="mt-2")

    tabs = dbc.Tabs([
        dbc.Tab(label="Executive", tab_id="ov"),
        dbc.Tab(label="Stores", tab_id="stores"),
        dbc.Tab(label="Products", tab_id="products"),
        dbc.Tab(label="Store × Product", tab_id="sp"),
        dbc.Tab(label="Anomalies", tab_id="anom"),
        dbc.Tab(label="Suggested Orders", tab_id="orders"),
        dbc.Tab(label="Explorer", tab_id="exp"),
        dbc.Tab(label="Predictive", tab_id="pred"),
    ], id="epos-tabs", active_tab="ov", className="mt-3")

    return dbc.Container([
        html.Div([
            header,
            side,   # Duracell prominent on the side
            controls,
            actions,
            tabs,
            html.Div(id="epos-body", className="mt-3"),
            footer, # Synovia footer across bottom
        ], className="fusion-page has-side-brand")
    ], fluid=True, className="pt-4 pb-5")

def _overview(selected_key: str):
    base = load_base(ttl=300)
    sw = base.store_weekly.copy()
    sw["CalendarKey"] = sw["CalendarKey"].astype(str)

    cur = sw[sw["CalendarKey"] == str(selected_key)].copy()
    if cur.empty:
        return dbc.Alert("No rows for selected week.", color="info")

    total_units = float(pd.to_numeric(cur.get("Units", 0), errors="coerce").fillna(0).sum())
    total_value = float(pd.to_numeric(cur.get("Value", 0), errors="coerce").fillna(0).sum())

    tw = sw.dropna(subset=["Start_Date"]).groupby(["CalendarKey","Start_Date"], as_index=False).agg(Units=("Units","sum"), Value=("Value","sum")).sort_values("Start_Date")
    cur_row = tw[tw["CalendarKey"] == str(selected_key)]
    cur_row = cur_row.iloc[0] if not cur_row.empty else tw.iloc[-1]
    idx = tw.index[tw["CalendarKey"] == str(cur_row["CalendarKey"])][0]
    prev_row = tw.iloc[idx-1] if idx > 0 else cur_row
    wow_units = ((total_units - float(prev_row["Units"])) / float(prev_row["Units"]) * 100.0) if float(prev_row["Units"]) else None
    wow_value = ((total_value - float(prev_row["Value"])) / float(prev_row["Value"]) * 100.0) if float(prev_row["Value"]) else None

    top = cur.groupby("Store_Name", as_index=False).agg(Units=("Units","sum"), Value=("Value","sum")).sort_values("Units", ascending=False).head(15)
    fig_top = go.Figure(go.Bar(x=top["Units"], y=top["Store_Name"], orientation="h", name="Units"))
    fig_top.update_layout(title="Top Stores (Units)")

    trend = tw.tail(26)
    fig_tr = go.Figure(go.Scatter(x=trend["Start_Date"], y=trend["Units"], mode="lines+markers", name="Units"))
    fig_tr.update_layout(title="Units Trend (26 weeks)")

    # Suggested Orders (rate-of-sale → cases)
    orders_df = _compute_suggested_orders(
        week=str(selected_key),
        store=None,
        cover_weeks=1,
        safety_pct=10,
        default_units_per_case=12,
        limit=250,
    )
    if orders_df is None or orders_df.empty:
        orders_value = "0 lines"
        orders_hint = "No suggestions (check data / pack sizes)"
    else:
        orders_value = f"{len(orders_df)} lines"
        try:
            total_cases = int(pd.to_numeric(orders_df["Suggested_Cases"], errors="coerce").fillna(0).sum())
        except Exception:
            total_cases = 0
        orders_hint = f"{total_cases} cases • click Review"

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("Units (week)", num(total_units), f"WoW: {pct(wow_units)}"), md=3),
            dbc.Col(kpi("Value (week)", money(total_value), f"WoW: {pct(wow_value)}"), md=3),
            dbc.Col(kpi("Stores active", num(cur["Store_Name"].nunique()), "Stores with sales"), md=3),
            dbc.Col(kpi_action("Suggested Orders", orders_value, orders_hint, "go-orders", "Review"), md=3),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_tr, 360), md=6), dbc.Col(graph(fig_top, 520), md=6)], className="g-3 mt-2"),
        dbc.Alert("Tip: choose a store or product in the controls to unlock deeper views.", color="secondary", className="mt-3"),
    ], fluid=True, className="p-0")

def _stores(selected_key: str, store_name: str | None):
    base = load_base(ttl=300)
    sw = base.store_weekly.copy()
    sw["CalendarKey"] = sw["CalendarKey"].astype(str)

    cur = sw[sw["CalendarKey"] == str(selected_key)].copy()
    if cur.empty:
        return dbc.Alert("No store rows for selected week.", color="info")

    # default store: top by Units
    if not store_name:
        t = cur.groupby("Store_Name", as_index=False).agg(Units=("Units","sum")).sort_values("Units", ascending=False)
        store_name = str(t.iloc[0]["Store_Name"]) if not t.empty else None

    if not store_name:
        return dbc.Alert("No store selected.", color="info")

    sh = sw[sw["Store_Name"].astype(str) == str(store_name)].dropna(subset=["Start_Date"]).sort_values("Start_Date")
    if sh.empty:
        return dbc.Alert("No history for selected store.", color="info")

    cur_store = cur[cur["Store_Name"].astype(str) == str(store_name)]
    cur_units = float(pd.to_numeric(cur_store.get("Units", 0), errors="coerce").fillna(0).sum())
    cur_value = float(pd.to_numeric(cur_store.get("Value", 0), errors="coerce").fillna(0).sum())

    # WoW for this store
    last26 = sh.tail(26).copy()
    wow_u = None
    wow_v = None
    if len(sh) >= 2:
        prev = sh.iloc[-2]
        last = sh.iloc[-1]
        wow_u = ((float(last["Units"]) - float(prev["Units"])) / float(prev["Units"]) * 100.0) if float(prev["Units"]) else None
        wow_v = ((float(last["Value"]) - float(prev["Value"])) / float(prev["Value"]) * 100.0) if float(prev["Value"]) else None

    fig_u = go.Figure(go.Scatter(x=last26["Start_Date"], y=last26["Units"], mode="lines+markers", name="Units"))
    fig_u.update_layout(title=f"{store_name} — Units (26 weeks)")

    fig_v = go.Figure(go.Scatter(x=last26["Start_Date"], y=last26["Value"], mode="lines+markers", name="Value"))
    fig_v.update_layout(title=f"{store_name} — Value (26 weeks)")

    # Top products for this store in selected week
    sp = qdf(SQL_STOREPROD_WEEKLY_BY_WEEK_STORE, [str(selected_key), str(store_name)], ttl=120)
    top_prod = None
    if not sp.empty and "Units" in sp.columns:
        sp["Units"] = pd.to_numeric(sp["Units"], errors="coerce").fillna(0.0)
        sp["Value"] = pd.to_numeric(sp["Value"], errors="coerce").fillna(0.0) if "Value" in sp.columns else 0.0
        sp["Label"] = sp["Dynamics_Code"].astype(str) + " — " + sp.get("Product_Description", "").astype(str)
        top_prod = sp.groupby("Label", as_index=False).agg(Units=("Units","sum")).sort_values("Units", ascending=False).head(15)
        fig_tp = go.Figure(go.Bar(x=top_prod["Units"], y=top_prod["Label"], orientation="h"))
        fig_tp.update_layout(title="Top Products in Store (Units)")
    else:
        fig_tp = go.Figure()
        fig_tp.update_layout(title="Top Products in Store (Units)")

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("Store", str(store_name), "Selected store"), md=3),
            dbc.Col(kpi("Units (week)", num(cur_units), f"WoW: {pct(wow_u)}"), md=3),
            dbc.Col(kpi("Value (week)", money(cur_value), f"WoW: {pct(wow_v)}"), md=3),
            dbc.Col(kpi("SKUs sold", num(sp["Dynamics_Code"].nunique()) if not sp.empty and "Dynamics_Code" in sp.columns else "0", "This week"), md=3),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_u, 360), md=6), dbc.Col(graph(fig_v, 360), md=6)], className="g-3 mt-2"),
        dbc.Row([dbc.Col(graph(fig_tp, 560), md=12)], className="g-3 mt-2"),
    ], fluid=True, className="p-0")

def _products(selected_key: str, product_code: str | None):
    base = load_base(ttl=300)
    pw = base.product_weekly.copy()
    pw["CalendarKey"] = pw["CalendarKey"].astype(str)

    cur = pw[pw["CalendarKey"] == str(selected_key)].copy()
    if cur.empty:
        return dbc.Alert("No product rows for selected week.", color="info")

    # default product: top by Units
    if not product_code:
        t = cur.groupby("Dynamics_Code", as_index=False).agg(Units=("Units","sum")).sort_values("Units", ascending=False)
        product_code = str(t.iloc[0]["Dynamics_Code"]) if not t.empty else None

    if not product_code:
        return dbc.Alert("No product selected.", color="info")

    ph = pw[pw["Dynamics_Code"].astype(str) == str(product_code)].dropna(subset=["Start_Date"]).sort_values("Start_Date")
    if ph.empty:
        return dbc.Alert("No history for selected product.", color="info")

    cur_prod = cur[cur["Dynamics_Code"].astype(str) == str(product_code)]
    cur_units = float(pd.to_numeric(cur_prod.get("Units", 0), errors="coerce").fillna(0).sum())
    cur_value = float(pd.to_numeric(cur_prod.get("Value", 0), errors="coerce").fillna(0).sum())

    # WoW for this product
    wow_u = None
    wow_v = None
    if len(ph) >= 2:
        prev = ph.iloc[-2]
        last = ph.iloc[-1]
        wow_u = ((float(last["Units"]) - float(prev["Units"])) / float(prev["Units"]) * 100.0) if float(prev["Units"]) else None
        wow_v = ((float(last["Value"]) - float(prev["Value"])) / float(prev["Value"]) * 100.0) if float(prev["Value"]) else None

    last26 = ph.tail(26)
    fig_u = go.Figure(go.Scatter(x=last26["Start_Date"], y=last26["Units"], mode="lines+markers"))
    fig_u.update_layout(title=f"{product_code} — Units (26 weeks)")

    fig_v = go.Figure(go.Scatter(x=last26["Start_Date"], y=last26["Value"], mode="lines+markers"))
    fig_v.update_layout(title=f"{product_code} — Value (26 weeks)")

    # Top stores for this product this week
    sp = qdf(SQL_STOREPROD_WEEKLY_BY_WEEK_PRODUCT, [str(selected_key), str(product_code)], ttl=120)
    if not sp.empty and "Units" in sp.columns and "Store_Name" in sp.columns:
        sp["Units"] = pd.to_numeric(sp["Units"], errors="coerce").fillna(0.0)
        top_st = sp.groupby("Store_Name", as_index=False).agg(Units=("Units","sum")).sort_values("Units", ascending=False).head(15)
        fig_ts = go.Figure(go.Bar(x=top_st["Units"], y=top_st["Store_Name"], orientation="h"))
        fig_ts.update_layout(title="Top Stores for SKU (Units)")
    else:
        fig_ts = go.Figure()
        fig_ts.update_layout(title="Top Stores for SKU (Units)")

    desc = ""
    if "Product_Description" in ph.columns:
        desc = str(ph["Product_Description"].dropna().iloc[-1]) if not ph["Product_Description"].dropna().empty else ""

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("SKU", str(product_code), desc), md=4),
            dbc.Col(kpi("Units (week)", num(cur_units), f"WoW: {pct(wow_u)}"), md=4),
            dbc.Col(kpi("Value (week)", money(cur_value), f"WoW: {pct(wow_v)}"), md=4),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_u, 360), md=6), dbc.Col(graph(fig_v, 360), md=6)], className="g-3 mt-2"),
        dbc.Row([dbc.Col(graph(fig_ts, 560), md=12)], className="g-3 mt-2"),
    ], fluid=True, className="p-0")

def _store_product(selected_key: str, store_name: str | None, product_code: str | None):
    if not store_name or not product_code:
        return dbc.Alert("Pick both a Store and a Product in the controls.", color="info")

    df = qdf(SQL_STOREPROD_HISTORY, [str(store_name), str(product_code)], ttl=120)
    if df.empty:
        return dbc.Alert("No history for selected Store × Product.", color="info")

    if "Start_Date" in df.columns:
        df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    df = df.sort_values("Start_Date")

    # Basic KPIs
    last = df.dropna(subset=["Start_Date"]).tail(1)
    units = float(pd.to_numeric(last.get("Units", 0), errors="coerce").fillna(0).iloc[0]) if not last.empty else 0.0
    value = float(pd.to_numeric(last.get("Value", 0), errors="coerce").fillna(0).iloc[0]) if not last.empty else 0.0

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Start_Date"], y=pd.to_numeric(df.get("Units", 0), errors="coerce").fillna(0), mode="lines+markers", name="Units"))
    fig.update_layout(title="Store × Product — Units history")

    # Change points (if ruptures installed)
    cps = detect_change_points(df, "Units", "Start_Date", max_breaks=2)
    for cp in cps:
        fig.add_vline(x=cp, line_dash="dash", line_width=2)

    return dbc.Container([
        dbc.Row([
            dbc.Col(kpi("Store", str(store_name), ""), md=4),
            dbc.Col(kpi("SKU", str(product_code), ""), md=4),
            dbc.Col(kpi("Latest Units", num(units), f"Latest Value: {money(value)}"), md=4),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig, 420), md=12)], className="g-3 mt-2"),
        dbc.Alert("Tip: dashed lines mark detected regime changes (change-point detection).", color="secondary", className="mt-3") if cps else html.Div()
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
        data=tf.sort_values("ML_AnomalyScore", ascending=False).head(500).to_dict("records"),
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
        dbc.Row([
            dbc.Col(graph(fig, 560), md=6),
            dbc.Col(dbc.Card(dbc.CardBody([html.Div("Anomaly Table", className="section-title"), table])), md=6)
        ], className="g-3 mt-2"),
        dbc.Alert("Anomalies are loaded from CUR.vw_StoreProductAnomalies_4W for the selected week.", color="secondary", className="mt-3")
    ], fluid=True, className="p-0")


def _orders_summary(rows: list[dict]) -> html.Div:
    if not rows:
        return html.Div("No suggestions for the current filters.", className="muted")

    total_lines = len(rows)
    total_cases = int(sum(float(r.get("Suggested_Cases") or 0) for r in rows))
    total_units = int(sum(float(r.get("Suggested_Units") or 0) for r in rows))
    yes = sum(1 for r in rows if str(r.get("Approve", "")).lower() == "yes")
    no = sum(1 for r in rows if str(r.get("Approve", "")).lower() == "no")

    return html.Div(
        [
            html.Span(f"Lines: {total_lines}  •  Units: {total_units:,}  •  Cases: {total_cases:,}"),
            html.Span(f"  •  Approved: {yes}  •  Rejected: {no}", className="ms-2 muted"),
        ]
    )


def _compute_suggested_orders(
    week: str,
    store: str | None,
    cover_weeks: float = 1.0,
    safety_pct: float = 10.0,
    default_units_per_case: int = 12,
    limit: int = 250,
) -> pd.DataFrame:
    """Compute suggested replenishment orders (cases) using 4-week rate-of-sale.

    Notes:
    - EPOS sales are in units.
    - Replenishment is in full cases. We convert using CFG.ReplenishmentPack.Units_Per_Case
      (fallback to default_units_per_case when missing).
    """
    df = qdf(SQL_STOREPROD_ANOM_4W_BY_WEEK, [week], ttl=300)
    if df.empty:
        return df

    d = df.copy()

    # Filter store (location) if provided
    if store:
        d = d[d.get("Store_Name").astype(str) == str(store)]

    # Numeric hygiene
    d["Units"] = pd.to_numeric(d.get("Units"), errors="coerce").fillna(0.0)
    d["Base_Units_4W"] = pd.to_numeric(d.get("Base_Units_4W"), errors="coerce").fillna(0.0)

    # Rate-of-sale: 4-week baseline average per week; fallback to current week units if baseline missing
    d["Rate_Units_per_Week"] = d["Base_Units_4W"] / 4.0
    missing_rate = d["Rate_Units_per_Week"] <= 0
    if missing_rate.any():
        d.loc[missing_rate, "Rate_Units_per_Week"] = d.loc[missing_rate, "Units"]

    # Forecast consumption over cover window + safety
    cw = float(cover_weeks or 1.0)
    sp = float(safety_pct or 0.0) / 100.0
    d["Forecast_Units"] = d["Rate_Units_per_Week"] * cw * (1.0 + sp)

    # Suggested units (round up to whole units)
    d["Suggested_Units"] = d["Forecast_Units"].apply(lambda x: int(math.ceil(x)) if x and x > 0 else 0)

    # Pack sizes (units per case)
    d["Dynamics_Code"] = d.get("Dynamics_Code").astype(str)
    pack = load_pack_sizes(ttl=3600)
    if not pack.empty and "Dynamics_Code" in pack.columns:
        d = d.merge(pack, how="left", on="Dynamics_Code")
    else:
        d["Units_Per_Case"] = None
        d["Case_Multiple"] = 1

    # Track whether the pack size was mapped or defaulted
    _upc_raw = pd.to_numeric(d.get("Units_Per_Case"), errors="coerce")
    had_pack = _upc_raw.notna()

    d["Units_Per_Case"] = (
        _upc_raw.fillna(default_units_per_case)
        .replace(0, default_units_per_case)
        .astype(int)
    )
    d["Case_Multiple"] = pd.to_numeric(d.get("Case_Multiple", 1), errors="coerce").fillna(1).astype(int)

    d["Pack_Source"] = had_pack.apply(lambda x: "Mapped" if bool(x) else "Default")

    # Convert to cases (round up to full cases, then to any case multiple)
    d["Suggested_Cases_Raw"] = (d["Suggested_Units"] / d["Units_Per_Case"]).apply(lambda x: int(math.ceil(x)) if x and x > 0 else 0)

    def _round_multiple(cases: int, multiple: int) -> int:
        m = max(int(multiple or 1), 1)
        if cases <= 0:
            return 0
        return int(math.ceil(cases / m) * m)

    d["Suggested_Cases"] = d.apply(lambda r: _round_multiple(int(r["Suggested_Cases_Raw"]), int(r["Case_Multiple"])), axis=1)

    # Keep meaningful suggestions
    d = d[d["Suggested_Cases"] > 0].copy()

    # Rank: biggest order first
    d = d.sort_values(["Suggested_Cases", "Suggested_Units"], ascending=[False, False])

    keep_cols = [
        "Store_Name",
        "Dynamics_Code",
        "Product_Description",
        "Units",
        "Rate_Units_per_Week",
        "Suggested_Units",
        "Units_Per_Case",
        "Case_Multiple",
        "Suggested_Cases",
        "Pack_Source",
    ]
    for c in keep_cols:
        if c not in d.columns:
            d[c] = None

    out = d[keep_cols].head(int(limit)).copy()
    out.rename(
        columns={
            "Store_Name": "Store",
            "Dynamics_Code": "Dynamics_Code",
            "Product_Description": "Product",
            "Units": "EPOS_Units_ThisWeek",
            "Rate_Units_per_Week": "Rate_Units_PerWeek",
        },
        inplace=True,
    )
    out["Approve"] = ""
    return out


def _suggested_orders(week: str, store: str | None) -> dbc.Container:
    # Defaults (user can tweak)
    default_cover = 1
    default_safety = 10
    default_upc = 12  # fallback when pack size mapping isn't available

    df = _compute_suggested_orders(
        week=week,
        store=store,
        cover_weeks=default_cover,
        safety_pct=default_safety,
        default_units_per_case=default_upc,
        limit=250,
    )
    rows = df.to_dict("records") if not df.empty else []

    controls = dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.H4("Suggested Orders", className="mb-1"),
                        html.Div(
                            "Rate-of-sale driven replenishment suggestions (EPOS units → full cases). "
                            "Approve lines, then export as JSON for downstream ordering.",
                            className="muted",
                        ),
                    ],
                    className="mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label("Weeks of cover"),
                                dcc.Slider(
                                    id="orders-cover",
                                    min=1,
                                    max=4,
                                    step=1,
                                    value=default_cover,
                                    marks={i: str(i) for i in range(1, 5)},
                                ),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Safety %"),
                                dcc.Slider(
                                    id="orders-safety",
                                    min=0,
                                    max=50,
                                    step=5,
                                    value=default_safety,
                                    marks={0: "0", 10: "10", 20: "20", 30: "30", 40: "40", 50: "50"},
                                ),
                            ],
                            md=4,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Default Units / Case (fallback)"),
                                dbc.Input(
                                    id="orders-default-upc",
                                    type="number",
                                    min=1,
                                    step=1,
                                    value=default_upc,
                                ),
                                html.Div("Tip: load CFG.ReplenishmentPack to avoid defaults.", className="muted mt-1"),
                            ],
                            md=4,
                        ),
                    ],
                    className="g-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label("Order location (free text)"),
                                dbc.Input(
                                    id="orders-location",
                                    placeholder="e.g., Store name / depot / route",
                                    value=store or "",
                                ),
                            ],
                            md=6,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Order reference"),
                                dbc.Input(
                                    id="orders-ref",
                                    placeholder="e.g., PO-12345 / Week 2601",
                                    value=f"Week {week}",
                                ),
                            ],
                            md=6,
                        ),
                    ],
                    className="g-3 mt-1",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("Mark all YES", id="orders-yes-all", color="success", className="me-2"),
                            md="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Mark all NO", id="orders-no-all", color="secondary", className="me-2"),
                            md="auto",
                        ),
                        dbc.Col(
                            dbc.Button("Export approved lines as JSON", id="orders-export-json", color="primary"),
                            md="auto",
                        ),
                        dbc.Col(html.Div(id="orders-summary", children=_orders_summary(rows)), md=True),
                    ],
                    className="g-2 align-items-center mt-3",
                ),
                dcc.Download(id="orders-json-download"),
                dcc.Store(id="orders-context", data={"week": week, "store": store}),
            ]
        ),
        className="mb-3",
    )

    table = dash_table.DataTable(
        id="orders-table",
        columns=[
            {"name": "Approve (Yes/No)", "id": "Approve", "presentation": "dropdown"},
            {"name": "Store", "id": "Store"},
            {"name": "Dynamics Code", "id": "Dynamics_Code"},
            {"name": "Product", "id": "Product"},
            {"name": "EPOS Units (This Week)", "id": "EPOS_Units_ThisWeek", "type": "numeric"},
            {"name": "Rate (Units / Week)", "id": "Rate_Units_PerWeek", "type": "numeric"},
            {"name": "Suggested Units", "id": "Suggested_Units", "type": "numeric"},
            {"name": "Units / Case", "id": "Units_Per_Case", "type": "numeric", "editable": True},
            {"name": "Case Multiple", "id": "Case_Multiple", "type": "numeric"},
            {"name": "Suggested Cases", "id": "Suggested_Cases", "type": "numeric"},
            {"name": "Pack Source", "id": "Pack_Source"},
        ],
        data=rows,
        editable=True,
        dropdown={
            "Approve": {
                "options": [
                    {"label": "", "value": ""},
                    {"label": "Yes", "value": "Yes"},
                    {"label": "No", "value": "No"},
                ]
            }
        },
        filter_action="native",
        sort_action="native",
        page_action="native",
        page_size=20,
        style_table={"overflowX": "auto"},
        style_cell={
            "padding": "8px",
            "fontFamily": "Montserrat, Segoe UI, Arial",
            "fontSize": "13px",
            "whiteSpace": "normal",
            "height": "auto",
            "minWidth": "120px",
            "width": "120px",
            "maxWidth": "360px",
        },
        style_header={
            "backgroundColor": "#0b1533",
            "color": "white",
            "fontWeight": "700",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{Approve} = "Yes"'},
                "fontWeight": "700",
            },
            {
                "if": {"filter_query": '{Pack_Source} = "Default"'},
                "color": "#b45309",
            },
        ],
    )

    return dbc.Container([controls, table], fluid=True)


def _explorer(selected_key: str):
    df = qdf(SQL_STOREPROD_WEEKLY_BY_WEEK, [str(selected_key)], ttl=120)
    if df.empty:
        return dbc.Alert("No Store×Product weekly rows for this week.", color="info")

    cols = [c for c in ["Store_Name","Dynamics_Code","Product_Description","Units","Value","CalendarKey","Start_Date"] if c in df.columns]
    df = df[cols].copy()
    if "Start_Date" in df.columns:
        df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.head(3000)

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

    # Two models: ridge (always) + holt-winters (if available)
    fu_r = forecast_next(tw, "Units", "Start_Date")
    fv_r = forecast_next(tw, "Value", "Start_Date")

    fu_hw, fu_sigma = holt_winters_forecast(tw, "Units", "Start_Date")
    fv_hw, fv_sigma = holt_winters_forecast(tw, "Value", "Start_Date")

    hist = tw.tail(52).copy()
    next_date = hist["Start_Date"].iloc[-1] + pd.Timedelta(days=7)

    def band(yhat, sigma):
        if yhat is None or sigma is None:
            return None
        lo = max(0.0, yhat - 1.96 * sigma)
        hi = max(0.0, yhat + 1.96 * sigma)
        return (lo, hi)

    bu = band(fu_hw, fu_sigma)
    bv = band(fv_hw, fv_sigma)

    fig_u = go.Figure()
    fig_u.add_trace(go.Scatter(x=hist["Start_Date"], y=hist["Units"], mode="lines+markers", name="Actual"))
    if fu_hw is not None:
        fig_u.add_trace(go.Scatter(x=[next_date], y=[fu_hw], mode="markers", marker={"size": 14}, name="HW Forecast"))
        if bu:
            fig_u.add_trace(go.Scatter(x=[next_date, next_date], y=[bu[0], bu[1]], mode="lines", name="95% band"))
    elif fu_r is not None:
        fig_u.add_trace(go.Scatter(x=[next_date], y=[fu_r], mode="markers", marker={"size": 14}, name="Ridge Forecast"))
    fig_u.update_layout(title="Units Forecast (Holt-Winters if available)")

    fig_v = go.Figure()
    fig_v.add_trace(go.Scatter(x=hist["Start_Date"], y=hist["Value"], mode="lines+markers", name="Actual"))
    if fv_hw is not None:
        fig_v.add_trace(go.Scatter(x=[next_date], y=[fv_hw], mode="markers", marker={"size": 14}, name="HW Forecast"))
        if bv:
            fig_v.add_trace(go.Scatter(x=[next_date, next_date], y=[bv[0], bv[1]], mode="lines", name="95% band"))
    elif fv_r is not None:
        fig_v.add_trace(go.Scatter(x=[next_date], y=[fv_r], mode="markers", marker={"size": 14}, name="Ridge Forecast"))
    fig_v.update_layout(title="Value Forecast (Holt-Winters if available)")

    return dbc.Container([
        dbc.Alert("Predictive analytics: Holt‑Winters (if installed) + ridge fallback, with optional confidence proxy.", color="primary"),
        dbc.Row([
            dbc.Col(kpi("Units forecast (next week)", num(fu_hw if fu_hw is not None else fu_r), "Model: HW/Ridge"), md=6),
            dbc.Col(kpi("Value forecast (next week)", money(fv_hw if fv_hw is not None else fv_r), "Model: HW/Ridge"), md=6),
        ], className="g-3"),
        dbc.Row([dbc.Col(graph(fig_u, 380), md=6), dbc.Col(graph(fig_v, 380), md=6)], className="g-3 mt-2"),
    ], fluid=True, className="p-0")


def safe_build_layout(asset_url):
    """Wrap build_layout so *any* exception becomes a visible error panel (and logs a traceback)."""
    try:
        return build_layout(asset_url)
    except Exception as e:
        import traceback
        print("[EPOS] Layout crashed:", e)
        print(traceback.format_exc())
        return dbc.Container(
            [
                dbc.Alert(
                    [
                        html.H4("EPOS layout failed to render", className="alert-heading"),
                        html.Div(
                            "Check Render logs for the stack trace. This is usually caused by a missing column/view "
                            "or a temporary database connectivity issue."
                        ),
                        html.Hr(),
                        html.Pre(str(e), style={"whiteSpace": "pre-wrap"}),
                    ],
                    color="danger",
                )
            ],
            fluid=True,
            className="pt-4",
        )

def create_epos_dash_app(server):
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname=BASE,
        assets_folder=str(ASSETS_DIR),
        external_stylesheets=[dbc.themes.FLATLY],
        title="Fusion EPOS",
        suppress_callback_exceptions=True,
    )

    def asset_url(filename: str) -> str:
        return app.get_asset_url(filename)

    # Keep the initial layout *static* so Dash doesn't try to build the full (DB-backed) layout
    # during component-suites requests (e.g. plotly.min.js). We render the real UI via a callback.
    app.layout = dbc.Container(
        [
            dcc.Location(id="epos-url", refresh=False),
            html.Div(id="epos-root"),
        ],
        fluid=True,
        className="pt-2 pb-4",
    )

    @app.callback(Output("epos-root", "children"), Input("epos-url", "pathname"))
    def _render_epos_root(pathname):
        base_prefix = BASE.rstrip("/")
        if pathname and not pathname.startswith(base_prefix):
            return dbc.Container(
                [dbc.Alert(f"Route mismatch for EPOS module. Expected prefix: {base_prefix}", color="warning")],
                fluid=True,
                className="pt-4",
            )
        return safe_build_layout(asset_url)


    @app.callback(
        Output("epos-body", "children"),
        Input("epos-tabs", "active_tab"),
        Input("epos-week", "value"),
        Input("epos-store", "value"),
        Input("epos-product", "value"),
        Input("epos-thresh", "value"),
    )
    def render_body(tab, week, store, product, thresh):
        if not week:
            return dbc.Alert("Select a week.", color="info")
        if tab == "ov":
            return _overview(str(week))
        if tab == "stores":
            return _stores(str(week), store)
        if tab == "products":
            return _products(str(week), product)
        if tab == "sp":
            return _store_product(str(week), store, product)
        if tab == "anom":
            return _anomalies(str(week), int(thresh or 20))
        if tab == "orders":
            return _suggested_orders(str(week), store)
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

    @app.callback(
        Output("epos-week", "value"),
        Input("epos-clear-cache", "n_clicks"),
        State("epos-week", "value"),
        prevent_initial_call=True,
    )
    def clear_cache_btn(n, week):
        # Lazy import to avoid circular imports
        from .epos_data_access import clear_cache
        clear_cache()
        return week



    # Quick nav: tile button on Overview → Suggested Orders tab
    @app.callback(
        Output("epos-tabs", "active_tab"),
        Input("go-orders", "n_clicks"),
        prevent_initial_call=True,
    )
    def _go_orders(_n):
        return "orders"

    @app.callback(
        Output("orders-table", "data"),
        Output("orders-summary", "children"),
        Input("orders-cover", "value"),
        Input("orders-safety", "value"),
        Input("orders-default-upc", "value"),
        Input("orders-yes-all", "n_clicks"),
        Input("orders-no-all", "n_clicks"),
        Input("orders-table", "data_timestamp"),
        State("orders-context", "data"),
        State("orders-table", "data"),
        prevent_initial_call=True,
    )
    def _update_orders(cover, safety, default_upc, yes_all, no_all, table_ts, ctx_data, current_rows):
        trig = ctx.triggered_id
        rows = current_rows or []

        if trig in ("orders-yes-all", "orders-no-all") and rows:
            val = "Yes" if trig == "orders-yes-all" else "No"
            for r in rows:
                r["Approve"] = val
            return rows, _orders_summary(rows)

        if trig == "orders-table" and rows:
            # Recalculate cases if Units_Per_Case was edited in-table
            for r in rows:
                try:
                    upc = int(float(r.get("Units_Per_Case") or 0))
                    upc = upc if upc > 0 else 1
                except Exception:
                    upc = 1
                try:
                    mult = int(float(r.get("Case_Multiple") or 1))
                    mult = mult if mult > 0 else 1
                except Exception:
                    mult = 1
                try:
                    su = int(float(r.get("Suggested_Units") or 0))
                except Exception:
                    su = 0
                raw = int(math.ceil(su / upc)) if (su > 0 and upc > 0) else 0
                r["Suggested_Cases"] = int(math.ceil(raw / mult) * mult) if raw > 0 else 0
            return rows, _orders_summary(rows)

        # Recompute from source data (rate-of-sale → cases)
        week = str((ctx_data or {}).get("week") or "")
        store = (ctx_data or {}).get("store")

        df = _compute_suggested_orders(
            week=week,
            store=store,
            cover_weeks=float(cover or 1),
            safety_pct=float(safety or 0),
            default_units_per_case=int(default_upc or 12),
            limit=250,
        )
        new_rows = df.to_dict("records") if df is not None and (not df.empty) else []
        return new_rows, _orders_summary(new_rows)

    @app.callback(
        Output("orders-json-download", "data"),
        Input("orders-export-json", "n_clicks"),
        State("orders-context", "data"),
        State("orders-location", "value"),
        State("orders-ref", "value"),
        State("orders-table", "data"),
        prevent_initial_call=True,
    )
    def _export_orders_json(_n, ctx_data, location, order_ref, rows):
        if not rows:
            return no_update

        week = str((ctx_data or {}).get("week") or "")
        store = (ctx_data or {}).get("store")

        approved = [r for r in rows if str(r.get("Approve", "")).lower() == "yes"]

        # Week metadata (nice-to-have, also helps with 'date out of sync' confusion)
        week_meta = {"CalendarKey": week}
        try:
            cal = calendar_dimension(ttl=3600)
            hit = cal[cal["CalendarKey"].astype(str) == str(week)]
            if not hit.empty:
                r0 = hit.iloc[0]
                week_meta = {
                    "CalendarKey": str(r0.get("CalendarKey")),
                    "Dunnes_Year": int(r0.get("Dunnes_Year")) if pd.notnull(r0.get("Dunnes_Year")) else None,
                    "Dunnes_Week": int(r0.get("Dunnes_Week")) if pd.notnull(r0.get("Dunnes_Week")) else None,
                    "Start_Date": pd.to_datetime(r0.get("Start_Date")).date().isoformat() if pd.notnull(r0.get("Start_Date")) else None,
                    "End_Date": pd.to_datetime(r0.get("End_Date")).date().isoformat() if pd.notnull(r0.get("End_Date")) else None,
                    "ISO_Year": int(r0.get("ISO_Year")) if pd.notnull(r0.get("ISO_Year")) else None,
                    "ISO_Week_Start": int(r0.get("ISO_Week_Start")) if pd.notnull(r0.get("ISO_Week_Start")) else None,
                    "ISO_Week_End": int(r0.get("ISO_Week_End")) if pd.notnull(r0.get("ISO_Week_End")) else None,
                }
        except Exception:
            pass

        # Export lines (recalculate cases at export time to reflect any edits)
        lines = []
        for r in approved:
            try:
                upc = int(float(r.get("Units_Per_Case") or 0))
                upc = upc if upc > 0 else 1
            except Exception:
                upc = 1
            try:
                mult = int(float(r.get("Case_Multiple") or 1))
                mult = mult if mult > 0 else 1
            except Exception:
                mult = 1
            try:
                su = int(float(r.get("Suggested_Units") or 0))
            except Exception:
                su = 0
            raw = int(math.ceil(su / upc)) if (su > 0 and upc > 0) else 0
            cases = int(math.ceil(raw / mult) * mult) if raw > 0 else 0

            lines.append(
                {
                    "store": r.get("Store"),
                    "dynamics_code": r.get("Dynamics_Code"),
                    "product": r.get("Product"),
                    "epos_units_this_week": r.get("EPOS_Units_ThisWeek"),
                    "rate_units_per_week": r.get("Rate_Units_PerWeek"),
                    "suggested_units": su,
                    "units_per_case": upc,
                    "case_multiple": mult,
                    "suggested_cases": cases,
                }
            )

        payload = {
            "module": "Fusion EPOS",
            "generated_at_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "week": week_meta,
            "store_filter": store,
            "order_location": location or store or "",
            "order_reference": order_ref or f"Week {week}",
            "lines": lines,
        }

        fn_store = str(store).replace(" ", "_") if store else "ALL"
        filename = f"suggested_orders_{week}_{fn_store}.json"
        return dcc.send_string(json.dumps(payload, indent=2), filename=filename)

    return app
