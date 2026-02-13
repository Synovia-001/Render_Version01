from __future__ import annotations

import dash
from dash import html, dcc, dash_table, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
from flask import has_request_context
from flask_login import current_user

from ..data_access import user_can_access_url
from .core_data_access import fetch_object_counts, fetch_table_list, fetch_top_tables, fetch_table_preview

BASE = "/module/Core/"

def _kpi(title: str, value: str):
    return dbc.Card(dbc.CardBody([
        html.Div(title, className="kpi-title"),
        html.Div(value, className="kpi-value"),
    ]), className="kpi-card")

def build_layout():
    if not has_request_context():
        return html.Div()

    if not getattr(current_user, "is_authenticated", False):
        return dbc.Container([
            dbc.Alert(["Not logged in. ", html.A("Login", href="/login")], color="warning")
        ], className="pt-4")

    user_id = int(current_user.get_id())

    # Respect module access from portal DB
    if not user_can_access_url(user_id, "/module/Core"):
        return dbc.Container([
            dbc.Alert("You do not have access to Fusion Core.", color="danger"),
            html.A("Back to Home", href="/", className="btn btn-outline-primary btn-sm mt-2")
        ], className="pt-4")

    header = dbc.Row([
        dbc.Col(html.Div([
            html.H3("Fusion Core", className="mb-0"),
            html.Div("Live module (Core DB) — object KPIs + data explorer", className="subhead"),
        ]), md=10),
        dbc.Col(html.Div([
            html.A("Home", href="/", className="btn btn-outline-primary btn-sm me-2"),
            html.A("Logout", href="/logout", className="btn btn-outline-secondary btn-sm"),
        ], className="text-end"), md=2),
    ], className="align-items-center")

    try:
        counts = fetch_object_counts()
        top_tables = fetch_top_tables(10)
        tables = fetch_table_list()
    except Exception as e:
        return dbc.Container([
            header,
            dbc.Alert(f"Core module failed to load from DB: {type(e).__name__}: {e}", color="danger")
        ], fluid=True, className="pt-4 pb-5")

    fig = px.bar(top_tables, x="table", y="rows", title="Top tables by row count")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20))

    return dbc.Container([
        header,

        dbc.Row([
            dbc.Col(_kpi("Tables", str(counts["tables"])), md=4),
            dbc.Col(_kpi("Views", str(counts["views"])), md=4),
            dbc.Col(_kpi("Stored Procs", str(counts["procs"])), md=4),
        ], className="mt-3 g-3"),

        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig), md=12),
        ], className="mt-3"),

        html.H4("Data Explorer", className="mt-4"),

        dbc.Row([
            dbc.Col([
                dcc.Dropdown(
                    id="core-table",
                    options=[{"label": t, "value": t} for t in tables],
                    placeholder="Select a table…",
                    clearable=True
                ),
                html.Div(className="text-muted mt-2", children="Shows TOP 100 rows from selected table (Core DB).")
            ], md=6),
        ], className="mt-2"),

        html.Div(id="core-preview", className="mt-3"),

    ], fluid=True, className="pt-4 pb-5")

def create_core_dash_app(server):
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname=BASE,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title="Fusion Core",
        suppress_callback_exceptions=True
    )
    app.layout = build_layout

    @app.callback(
        Output("core-preview", "children"),
        Input("core-table", "value"),
    )
    def _preview_table(table_name):
        if not table_name:
            return dbc.Alert("Select a table to preview.", color="info")

        try:
            cols, data = fetch_table_preview(table_name, limit=100)
        except Exception as e:
            return dbc.Alert(f"Preview failed: {type(e).__name__}: {e}", color="danger")

        return dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in cols],
            data=data,
            page_size=20,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "fontFamily": "sans-serif", "fontSize": 13},
        )

    return app
