from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import dash
from dash import html, dcc, dash_table, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from flask import has_request_context
from flask_login import current_user

from ..data_access import user_can_access_url
from . import epos_data_access as da


BASE = "/module/EPOS/"


# ------------------------------
# UI helpers
# ------------------------------

def _kpi_card(title: str, value: str, hint: str = ""):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(hint, className="kpi-hint"),
        ]),
        className="kpi-card",
    )


def _fmt_num(x: Any) -> str:
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "—"


def _fmt_money(x: Any) -> str:
    try:
        return f"€{float(x):,.0f}"
    except Exception:
        return "—"


def _fmt_pct(x: Any) -> str:
    try:
        if x is None:
            return "—"
        return f"{float(x):+.1f}%"
    except Exception:
        return "—"


def _graph(graph_id: str, height_px: int = 340):
    return dcc.Graph(
        id=graph_id,
        style={"height": f"{height_px}px"},
        config={"displayModeBar": True, "responsive": True},
    )


def _table(table_id: str, page_size: int = 15):
    return dash_table.DataTable(
        id=table_id,
        page_size=page_size,
        style_table={"overflowX": "auto"},
        style_cell={
            "fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
            "fontSize": "0.9rem",
            "padding": "8px",
            "whiteSpace": "normal",
            "height": "auto",
            "minWidth": "80px",
            "maxWidth": "360px",
        },
        style_header={"fontWeight": "600"},
        sort_action="native",
        filter_action="native",
        page_action="native",
    )


# ------------------------------
# Dash app factory
# ------------------------------

def create_epos_dash_app(server):
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname=BASE,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title="Fusion EPOS",
        suppress_callback_exceptions=True,
    )

    def build_layout():
        # Dash may call layout at startup with no request context.
        if not has_request_context():
            return html.Div()

        if not getattr(current_user, "is_authenticated", False):
            return dbc.Container([
                dbc.Alert(["You are not logged in. ", html.A("Go to login", href="/login")], color="warning"),
            ], className="pt-4")

        user_id = int(current_user.get_id())
        if not user_can_access_url(user_id, "/module/EPOS"):
            return dbc.Container([
                dbc.Alert("You do not have access to Fusion EPOS.", color="danger"),
                html.A("Back to Console", href="/", className="btn btn-outline-secondary btn-sm")
            ], className="pt-4")

        # Load dimensions / defaults (safe, no huge data load)
        try:
            week_opts = da.build_week_options()
            latest_key = da.latest_calendar_key()
            stores = da.store_options()
            products = da.product_options()
            prod_map = da.product_label_map()
        except Exception as e:
            return dbc.Container([
                dbc.Alert(f"EPOS module could not load metadata: {type(e).__name__}: {e}", color="danger"),
                html.Div("Check EPOS_DB env var and that required CUR views exist in the EPOS database.", className="text-muted"),
                html.A("Back to Console", href="/", className="btn btn-outline-secondary btn-sm mt-3"),
            ], className="pt-4", fluid=True)

        header = dbc.Row([
            dbc.Col(html.Div([
                html.H3("Fusion EPOS", className="mb-0"),
                html.Div(
                    f"Welcome, {getattr(current_user, 'display_name', current_user.get_id())} • "
                    f"Role: {getattr(current_user, 'role', 'User')}",
                    className="subhead"
                ),
            ]), md=8),
            dbc.Col(html.Div([
                html.A("Back to Console", href="/", className="btn btn-outline-secondary btn-sm me-2"),
                html.A("Logout", href="/logout", className="btn btn-outline-secondary btn-sm"),
            ], className="text-end"), md=4),
        ], className="align-items-center")

        controls = dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Week", className="form-label mb-1"),
                    dcc.Dropdown(
                        id="epos-week",
                        options=week_opts,
                        value=latest_key,
                        clearable=False,
                    ),
                ], md=6),
                dbc.Col([
                    html.Label("Actions", className="form-label mb-1"),
                    html.Div([
                        dbc.Button("Refresh (clear cache)", id="epos-refresh", color="primary", outline=True, size="sm", className="me-2"),
                        dbc.Button("Download totals (CSV)", id="epos-dl-totals-btn", color="secondary", outline=True, size="sm"),
                        dcc.Download(id="epos-dl-totals"),
                    ])
                ], md=6),
            ], className="g-3"),
            dbc.Alert(id="epos-refresh-msg", color="info", className="mt-3 mb-0", is_open=False),
        ]), className="mt-3")

        tabs = dbc.Tabs([
            dbc.Tab(label="Overview", tab_id="tab-overview"),
            dbc.Tab(label="Stores", tab_id="tab-stores"),
            dbc.Tab(label="Products", tab_id="tab-products"),
            dbc.Tab(label="Store × Product", tab_id="tab-storeprod"),
            dbc.Tab(label="Anomalies", tab_id="tab-anomalies"),
            dbc.Tab(label="Data Explorer", tab_id="tab-explorer"),
        ], id="epos-tabs", active_tab="tab-overview", className="mt-4")

        content = html.Div(id="epos-tab-content", className="mt-3")

        return dbc.Container([
            dcc.Store(id="epos-prod-map", data=prod_map),
            header,
            controls,
            tabs,
            content,
            html.Hr(),
            html.Div("Tip: Set EPOS_DB in Render env vars to switch the EPOS module database.", className="footer-tip"),
        ], fluid=True, className="pt-4 pb-5")

    app.layout = build_layout

    # ------------------------------
    # Callbacks: refresh + shared data
    # ------------------------------

    @app.callback(
        Output("epos-refresh-msg", "is_open"),
        Output("epos-refresh-msg", "children"),
        Input("epos-refresh", "n_clicks"),
        prevent_initial_call=True,
    )
    def _refresh_cache(n_clicks):
        da.clear_cache()
        return True, f"Cache cleared at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

    @app.callback(
        Output("epos-dl-totals", "data"),
        Input("epos-dl-totals-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _dl_totals(_):
        df = da.totals_by_week()
        return dcc.send_data_frame(df.to_csv, "epos_totals_by_week.csv", index=False)

    # ------------------------------
    # Tab router
    # ------------------------------

    @app.callback(
        Output("epos-tab-content", "children"),
        Input("epos-tabs", "active_tab"),
    )
    def _render_tab(tab_id):
        if tab_id == "tab-overview":
            return _layout_overview()
        if tab_id == "tab-stores":
            return _layout_stores()
        if tab_id == "tab-products":
            return _layout_products()
        if tab_id == "tab-storeprod":
            return _layout_storeprod()
        if tab_id == "tab-anomalies":
            return _layout_anomalies()
        if tab_id == "tab-explorer":
            return _layout_explorer()
        return dbc.Alert("Unknown tab", color="warning")

    # ------------------------------
    # Layouts per tab
    # ------------------------------

    def _layout_overview():
        return html.Div([
            dbc.Row([
                dbc.Col(_kpi_card("Week Units", "—", "Units for selected week"), md=3, id="kpi-units-col"),
                dbc.Col(_kpi_card("Week Value", "—", "Value for selected week"), md=3, id="kpi-value-col"),
                dbc.Col(_kpi_card("WoW Units", "—", "vs previous week"), md=3, id="kpi-wow-units-col"),
                dbc.Col(_kpi_card("WoW Value", "—", "vs previous week"), md=3, id="kpi-wow-value-col"),
            ], className="g-3"),
            dbc.Row([
                dbc.Col(_graph("fig-total-trend-units", 320), md=6),
                dbc.Col(_graph("fig-total-trend-value", 320), md=6),
            ], className="mt-3 g-3"),
            dbc.Row([
                dbc.Col(_graph("fig-top-stores", 520), md=6),
                dbc.Col(_graph("fig-top-products", 520), md=6),
            ], className="mt-3 g-3"),
        ])

    def _layout_stores():
        return dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Store", className="form-label mb-1"),
                    dcc.Dropdown(id="store-name", options=da.store_options(), value=None, clearable=True, placeholder="Select a store..."),
                ], md=6),
                dbc.Col([
                    html.Label("Top N", className="form-label mb-1"),
                    dcc.Slider(id="store-topn", min=5, max=30, step=1, value=10, marks={5:"5",10:"10",20:"20",30:"30"}),
                ], md=6),
            ], className="g-3"),
            dbc.Row([
                dbc.Col(_graph("fig-store-units", 340), md=6),
                dbc.Col(_graph("fig-store-value", 340), md=6),
            ], className="mt-3 g-3"),
            html.Div("If no store is selected, the charts show the top stores for the selected week.", className="text-muted mt-2"),
        ]))

    def _layout_products():
        return dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Product", className="form-label mb-1"),
                    dcc.Dropdown(id="product-code", options=da.product_options(), value=None, clearable=True, placeholder="Select a product code..."),
                ], md=6),
                dbc.Col([
                    html.Label("Top N", className="form-label mb-1"),
                    dcc.Slider(id="product-topn", min=5, max=30, step=1, value=10, marks={5:"5",10:"10",20:"20",30:"30"}),
                ], md=6),
            ], className="g-3"),
            dbc.Row([
                dbc.Col(_graph("fig-product-units", 340), md=6),
                dbc.Col(_graph("fig-product-value", 340), md=6),
            ], className="mt-3 g-3"),
            html.Div("If no product is selected, the charts show the top products for the selected week.", className="text-muted mt-2"),
        ]))

    def _layout_storeprod():
        return dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Top stores (heatmap)", className="form-label mb-1"),
                    dcc.Slider(id="hm-top-stores", min=5, max=30, step=1, value=15, marks={5:"5",10:"10",15:"15",20:"20",30:"30"}),
                ], md=6),
                dbc.Col([
                    html.Label("Top products (heatmap)", className="form-label mb-1"),
                    dcc.Slider(id="hm-top-products", min=5, max=30, step=1, value=15, marks={5:"5",10:"10",15:"15",20:"20",30:"30"}),
                ], md=6),
            ], className="g-3"),
            dbc.Row([
                dbc.Col(_graph("fig-storeprod-heatmap", 640), md=12),
            ], className="mt-3 g-3"),
            dbc.Row([
                dbc.Col([
                    html.Label("Store (trend)", className="form-label mb-1"),
                    dcc.Dropdown(id="sp-store", options=da.store_options(), value=None, clearable=True),
                ], md=6),
                dbc.Col([
                    html.Label("Product (trend)", className="form-label mb-1"),
                    dcc.Dropdown(id="sp-product", options=da.product_options(), value=None, clearable=True),
                ], md=6),
            ], className="g-3 mt-1"),
            dbc.Row([
                dbc.Col(_graph("fig-storeprod-trend", 360), md=12),
            ], className="mt-3 g-3"),
        ]))

    def _layout_anomalies():
        return dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Button("Download anomalies (CSV)", id="epos-dl-anom-btn", color="secondary", outline=True, size="sm"),
                    dcc.Download(id="epos-dl-anom"),
                ], md=12),
            ]),
            html.Div("Top anomalies are loaded for the selected week from CUR.vw_StoreProductAnomalies_4W.", className="text-muted mt-2"),
            html.Div(_table("tbl-anomalies", page_size=20), className="mt-3"),
        ]))

    def _layout_explorer():
        view_opts = [
            {"label": "vw_WeeklySales_Fact", "value": "vw_WeeklySales_Fact"},
            {"label": "vw_StoreWeekly", "value": "vw_StoreWeekly"},
            {"label": "vw_ProductWeekly", "value": "vw_ProductWeekly"},
            {"label": "vw_StoreProductWeekly", "value": "vw_StoreProductWeekly"},
            {"label": "vw_StoreAnomalies_4W", "value": "vw_StoreAnomalies_4W"},
            {"label": "vw_StoreProductAnomalies_4W", "value": "vw_StoreProductAnomalies_4W"},
            {"label": "vw_StoreProductBaselines", "value": "vw_StoreProductBaselines"},
        ]

        return dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("View", className="form-label mb-1"),
                    dcc.Dropdown(id="ex-view", options=view_opts, value="vw_WeeklySales_Fact", clearable=False),
                ], md=6),
                dbc.Col([
                    html.Label("Row limit", className="form-label mb-1"),
                    dcc.Input(id="ex-limit", type="number", min=100, max=100000, step=100, value=2000, className="form-control"),
                ], md=3),
                dbc.Col([
                    html.Label(" ", className="form-label mb-1"),
                    dbc.Button("Run query", id="ex-run", color="primary", outline=True, className="w-100"),
                ], md=3),
            ], className="g-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Button("Download (CSV)", id="ex-dl-btn", color="secondary", outline=True, size="sm", className="mt-3"),
                    dcc.Download(id="ex-dl"),
                ], md=12),
            ]),
            dbc.Alert(id="ex-msg", color="warning", className="mt-3", is_open=False),
            html.Div(_table("ex-table", page_size=20), className="mt-3"),
        ]))

    # ------------------------------
    # Overview callbacks
    # ------------------------------

    @app.callback(
        Output("kpi-units-col", "children"),
        Output("kpi-value-col", "children"),
        Output("kpi-wow-units-col", "children"),
        Output("kpi-wow-value-col", "children"),
        Input("epos-week", "value"),
    )
    def _update_overview_kpis(week_key):
        if not week_key:
            return (
                _kpi_card("Week Units", "—"),
                _kpi_card("Week Value", "—"),
                _kpi_card("WoW Units", "—"),
                _kpi_card("WoW Value", "—"),
            )

        k = da.compute_overview_kpis(str(week_key))
        if not k:
            return (
                _kpi_card("Week Units", "—"),
                _kpi_card("Week Value", "—"),
                _kpi_card("WoW Units", "—"),
                _kpi_card("WoW Value", "—"),
            )

        start = k.get("cur_start")
        start_txt = start.date().isoformat() if hasattr(start, "date") and start else ""
        return (
            _kpi_card("Week Units", _fmt_num(k.get("cur_units")), f"Key {k.get('cur_key')} • {start_txt}"),
            _kpi_card("Week Value", _fmt_money(k.get("cur_value")), f"Key {k.get('cur_key')} • {start_txt}"),
            _kpi_card("WoW Units", _fmt_pct(k.get("wow_units_pct")), f"Prev: {_fmt_num(k.get('prev_units'))}"),
            _kpi_card("WoW Value", _fmt_pct(k.get("wow_value_pct")), f"Prev: {_fmt_money(k.get('prev_value'))}"),
        )

    @app.callback(
        Output("fig-total-trend-units", "figure"),
        Output("fig-total-trend-value", "figure"),
        Input("epos-week", "value"),
    )
    def _total_trend_figs(_week_key):
        df = da.totals_by_week()
        if df.empty:
            empty = go.Figure().update_layout(template="plotly_white", title="No data")
            return empty, empty

        fig_u = go.Figure()
        fig_u.add_trace(go.Scatter(x=df["Start_Date"], y=df["Units"], mode="lines+markers", name="Units"))
        fig_u.update_layout(template="plotly_white", title="Total Units (by week)", height=320, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

        fig_v = go.Figure()
        fig_v.add_trace(go.Scatter(x=df["Start_Date"], y=df["Value"], mode="lines+markers", name="Value"))
        fig_v.update_layout(template="plotly_white", title="Total Value (by week)", height=320, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

        return fig_u, fig_v

    @app.callback(
        Output("fig-top-stores", "figure"),
        Output("fig-top-products", "figure"),
        Input("epos-week", "value"),
    )
    def _top_figs(week_key):
        if not week_key:
            empty = go.Figure().update_layout(template="plotly_white", title="Select a week", height=520, autosize=False)
            return empty, empty

        top_stores = da.qdf(da.SQL_TOP_STORES_BY_WEEK, params=(10, str(week_key)))
        if not top_stores.empty:
            fig_s = px.bar(top_stores, x="Units", y="Store_Name", orientation="h", title="Top Stores (Units)")
            fig_s.update_layout(template="plotly_white", height=520, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
            fig_s.update_yaxes(automargin=True)
        else:
            fig_s = go.Figure().update_layout(template="plotly_white", title="Top Stores (Units)", height=520, autosize=False)

        top_products = da.qdf(da.SQL_TOP_PRODUCTS_BY_WEEK, params=(10, str(week_key)))
        if not top_products.empty:
            # create short label
            top_products = top_products.copy()
            top_products["Label"] = top_products["Dynamics_Code"].astype(str) + " — " + top_products["Product_Description"].astype(str).str.slice(0, 40)
            fig_p = px.bar(top_products, x="Units", y="Label", orientation="h", title="Top Products (Units)")
            fig_p.update_layout(template="plotly_white", height=520, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
            fig_p.update_yaxes(automargin=True)
        else:
            fig_p = go.Figure().update_layout(template="plotly_white", title="Top Products (Units)", height=520, autosize=False)

        return fig_s, fig_p

    # ------------------------------
    # Stores callbacks
    # ------------------------------

    @app.callback(
        Output("fig-store-units", "figure"),
        Output("fig-store-value", "figure"),
        Input("epos-week", "value"),
        Input("store-name", "value"),
        Input("store-topn", "value"),
    )
    def _store_figs(week_key, store_name, topn):
        if store_name:
            df = da.qdf(da.SQL_STORE_TREND, params=(store_name,), ttl=600)
            if "Start_Date" in df.columns:
                df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")

            fig_u = px.line(df, x="Start_Date", y="Units", title=f"Units Trend — {store_name}", markers=True)
            fig_u.update_layout(template="plotly_white", height=340, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

            fig_v = px.line(df, x="Start_Date", y="Value", title=f"Value Trend — {store_name}", markers=True)
            fig_v.update_layout(template="plotly_white", height=340, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

            return fig_u, fig_v

        # fallback: top stores by selected week
        if not week_key:
            empty = go.Figure().update_layout(template="plotly_white", title="Select a week", height=340, autosize=False)
            return empty, empty

        topn = int(topn or 10)
        df = da.qdf(da.SQL_TOP_STORES_BY_WEEK, params=(topn, str(week_key)))
        if df.empty:
            empty = go.Figure().update_layout(template="plotly_white", title="No data", height=340, autosize=False)
            return empty, empty

        fig_u = px.bar(df.sort_values("Units"), x="Units", y="Store_Name", orientation="h", title=f"Top {topn} Stores — Units")
        fig_u.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
        fig_u.update_yaxes(automargin=True)

        fig_v = px.bar(df.sort_values("Value"), x="Value", y="Store_Name", orientation="h", title=f"Top {topn} Stores — Value")
        fig_v.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
        fig_v.update_yaxes(automargin=True)

        return fig_u, fig_v

    # ------------------------------
    # Products callbacks
    # ------------------------------

    @app.callback(
        Output("fig-product-units", "figure"),
        Output("fig-product-value", "figure"),
        Input("epos-week", "value"),
        Input("product-code", "value"),
        Input("product-topn", "value"),
        State("epos-prod-map", "data"),
    )
    def _product_figs(week_key, product_code, topn, prod_map):
        if product_code:
            df = da.qdf(da.SQL_PRODUCT_TREND, params=(str(product_code),), ttl=600)
            try:
                import pandas as pd
                df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
            except Exception:
                pass

            label = (prod_map or {}).get(str(product_code), str(product_code))
            fig_u = px.line(df, x="Start_Date", y="Units", title=f"Units Trend — {label}", markers=True)
            fig_u.update_layout(template="plotly_white", height=340, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

            fig_v = px.line(df, x="Start_Date", y="Value", title=f"Value Trend — {label}", markers=True)
            fig_v.update_layout(template="plotly_white", height=340, margin=dict(l=30, r=10, t=50, b=30), autosize=False)

            return fig_u, fig_v

        # fallback: top products by selected week
        if not week_key:
            empty = go.Figure().update_layout(template="plotly_white", title="Select a week", height=340, autosize=False)
            return empty, empty

        topn = int(topn or 10)
        df = da.qdf(da.SQL_TOP_PRODUCTS_BY_WEEK, params=(topn, str(week_key)))
        if df.empty:
            empty = go.Figure().update_layout(template="plotly_white", title="No data", height=340, autosize=False)
            return empty, empty

        df = df.copy()
        df["Label"] = df["Dynamics_Code"].astype(str) + " — " + df["Product_Description"].astype(str).str.slice(0, 40)

        fig_u = px.bar(df.sort_values("Units"), x="Units", y="Label", orientation="h", title=f"Top {topn} Products — Units")
        fig_u.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
        fig_u.update_yaxes(automargin=True)

        fig_v = px.bar(df.sort_values("Value"), x="Value", y="Label", orientation="h", title=f"Top {topn} Products — Value")
        fig_v.update_layout(template="plotly_white", height=340, margin=dict(l=10, r=10, t=50, b=30), autosize=False, yaxis_title="")
        fig_v.update_yaxes(automargin=True)

        return fig_u, fig_v

    # ------------------------------
    # Store×Product heatmap + trend
    # ------------------------------

    @app.callback(
        Output("fig-storeprod-heatmap", "figure"),
        Input("epos-week", "value"),
        Input("hm-top-stores", "value"),
        Input("hm-top-products", "value"),
        State("epos-prod-map", "data"),
    )
    def _heatmap_fig(week_key, top_stores, top_products, prod_map):
        if not week_key:
            return go.Figure().update_layout(template="plotly_white", title="Select a week", height=640, autosize=False)

        top_stores = int(top_stores or 15)
        top_products = int(top_products or 15)

        df = da.qdf(da.SQL_STOREPROD_WEEKLY_BY_WEEK, params=(str(week_key),), ttl=600)
        if df.empty:
            return go.Figure().update_layout(template="plotly_white", title="No data", height=640, autosize=False)

        # Defensive: column names
        needed = {"Store_Name", "Dynamics_Code", "Units"}
        if not needed.issubset(set(df.columns)):
            return go.Figure().update_layout(template="plotly_white", title="View columns not as expected", height=640, autosize=False)

        # Pick top stores/products by units
        st = df.groupby("Store_Name", as_index=False)["Units"].sum().sort_values("Units", ascending=False).head(top_stores)
        pr = df.groupby("Dynamics_Code", as_index=False)["Units"].sum().sort_values("Units", ascending=False).head(top_products)
        keep_stores = set(st["Store_Name"].astype(str).tolist())
        keep_products = set(pr["Dynamics_Code"].astype(str).tolist())

        df2 = df[df["Store_Name"].astype(str).isin(keep_stores) & df["Dynamics_Code"].astype(str).isin(keep_products)].copy()
        if df2.empty:
            return go.Figure().update_layout(template="plotly_white", title="No data (after top-N filter)", height=640, autosize=False)

        # Friendly product label (short)
        if prod_map:
            df2["ProdLabel"] = df2["Dynamics_Code"].astype(str).map(lambda x: (prod_map.get(str(x), str(x))).split("—")[0].strip())
        else:
            df2["ProdLabel"] = df2["Dynamics_Code"].astype(str)

        try:
            import pandas as pd
            pv = pd.pivot_table(df2, index="Store_Name", columns="ProdLabel", values="Units", aggfunc="sum", fill_value=0)
        except Exception:
            return go.Figure().update_layout(template="plotly_white", title="Pivot failed", height=640, autosize=False)

        fig = px.imshow(
            pv,
            aspect="auto",
            labels=dict(x="Product", y="Store", color="Units"),
            title="Units Heatmap (Top Stores × Top Products)",
        )
        fig.update_layout(template="plotly_white", height=640, margin=dict(l=10, r=10, t=50, b=10), autosize=False)
        return fig

    @app.callback(
        Output("fig-storeprod-trend", "figure"),
        Input("sp-store", "value"),
        Input("sp-product", "value"),
    )
    def _storeprod_trend(store_name, product_code):
        if not store_name or not product_code:
            return go.Figure().update_layout(template="plotly_white", title="Select a store and product", height=360, autosize=False)

        sql = """
        SELECT CalendarKey, Start_Date, Store_Name, Dynamics_Code, Units, Value
        FROM CUR.vw_StoreProductWeekly
        WHERE Store_Name = ? AND Dynamics_Code = ?
        ORDER BY Start_Date;
        """
        df = da.qdf(sql, params=(str(store_name), str(product_code)), ttl=600)
        if df.empty:
            return go.Figure().update_layout(template="plotly_white", title="No data", height=360, autosize=False)

        try:
            import pandas as pd
            df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
        except Exception:
            pass

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Start_Date"], y=df["Units"], mode="lines+markers", name="Units"))
        fig.add_trace(go.Scatter(x=df["Start_Date"], y=df["Value"], mode="lines+markers", name="Value", yaxis="y2"))
        fig.update_layout(
            template="plotly_white",
            title=f"Store×Product Trend — {store_name} • {product_code}",
            height=360,
            margin=dict(l=30, r=10, t=50, b=30),
            autosize=False,
            yaxis=dict(title="Units"),
            yaxis2=dict(title="Value", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        return fig

    # ------------------------------
    # Anomalies callbacks
    # ------------------------------

    @app.callback(
        Output("tbl-anomalies", "data"),
        Output("tbl-anomalies", "columns"),
        Input("epos-week", "value"),
    )
    def _anom_table(week_key):
        if not week_key:
            return [], []

        df = da.qdf(da.SQL_STOREPROD_ANOM_4W_BY_WEEK, params=(str(week_key),), ttl=600)
        if df.empty:
            return [], []

        # Try to sort by largest deviation if columns exist
        for c in ["Units_Delta", "Value_Delta", "Units_Deviation", "Value_Deviation"]:
            if c in df.columns:
                df = df.sort_values(c, ascending=False)

        df = df.head(2000)  # protect UI
        cols = [{"name": c, "id": c} for c in df.columns]
        return df.to_dict("records"), cols

    @app.callback(
        Output("epos-dl-anom", "data"),
        Input("epos-dl-anom-btn", "n_clicks"),
        State("epos-week", "value"),
        prevent_initial_call=True,
    )
    def _dl_anom(_, week_key):
        if not week_key:
            return dash.no_update
        df = da.qdf(da.SQL_STOREPROD_ANOM_4W_BY_WEEK, params=(str(week_key),), ttl=1)
        return dcc.send_data_frame(df.to_csv, f"epos_anomalies_{week_key}.csv", index=False)

    # ------------------------------
    # Explorer callbacks
    # ------------------------------

    VIEW_SQL = {
        "vw_WeeklySales_Fact": da.SQL_WEEKLY_FACT_BY_WEEK,
        "vw_StoreWeekly": "SELECT * FROM CUR.vw_StoreWeekly WHERE CalendarKey = ?;",
        "vw_ProductWeekly": "SELECT * FROM CUR.vw_ProductWeekly WHERE CalendarKey = ?;",
        "vw_StoreProductWeekly": da.SQL_STOREPROD_WEEKLY_BY_WEEK,
        "vw_StoreAnomalies_4W": da.SQL_STORE_ANOM_4W_BY_WEEK,
        "vw_StoreProductAnomalies_4W": da.SQL_STOREPROD_ANOM_4W_BY_WEEK,
        "vw_StoreProductBaselines": da.SQL_STOREPROD_BASELINES_BY_WEEK,
    }

    @app.callback(
        Output("ex-table", "data"),
        Output("ex-table", "columns"),
        Output("ex-msg", "is_open"),
        Output("ex-msg", "children"),
        Input("ex-run", "n_clicks"),
        State("ex-view", "value"),
        State("epos-week", "value"),
        State("ex-limit", "value"),
        prevent_initial_call=True,
    )
    def _run_explorer(_, view_name, week_key, limit):
        if not week_key:
            return [], [], True, "Select a week first."
        if not view_name:
            return [], [], True, "Select a view."

        sql = VIEW_SQL.get(view_name)
        if not sql:
            return [], [], True, f"Unsupported view: {view_name}"

        # Apply TOP limit by wrapping if needed
        try:
            lim = int(limit or 2000)
        except Exception:
            lim = 2000
        lim = max(100, min(lim, 100000))

        # Wrap: SELECT TOP (lim) * FROM ( <sql without semicolon> ) x
        base_sql = sql.strip().rstrip(";")
        wrapped = f"SELECT TOP ({lim}) * FROM ({base_sql}) AS x;"

        try:
            df = da.qdf(wrapped, params=(str(week_key),), ttl=60)
        except Exception as e:
            return [], [], True, f"{type(e).__name__}: {e}"

        cols = [{"name": c, "id": c} for c in df.columns]
        return df.to_dict("records"), cols, False, ""

    @app.callback(
        Output("ex-dl", "data"),
        Input("ex-dl-btn", "n_clicks"),
        State("ex-view", "value"),
        State("epos-week", "value"),
        prevent_initial_call=True,
    )
    def _dl_explorer(_, view_name, week_key):
        if not week_key or not view_name:
            return dash.no_update
        sql = VIEW_SQL.get(view_name)
        if not sql:
            return dash.no_update
        df = da.qdf(sql, params=(str(week_key),), ttl=1)
        return dcc.send_data_frame(df.to_csv, f"{view_name}_{week_key}.csv", index=False)

    return app
