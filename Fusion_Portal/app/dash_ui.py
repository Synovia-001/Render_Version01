from __future__ import annotations

import dash
from dash import html
import dash_bootstrap_components as dbc
from flask import has_request_context
from flask_login import current_user

from .data_access import fetch_kpis_for_user, fetch_modules_for_user, fetch_user_profile

def kpi_tile(title: str, value: str, hint: str | None = None):
    return dbc.Card(
        dbc.CardBody([
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(hint or "", className="kpi-hint"),
        ]),
        className="kpi-card"
    )

def module_card(name: str, url: str, icon: str | None = None):
    icon_el = html.I(className=icon) if icon else html.Span("")
    return dbc.Card(
        dbc.CardBody([
            html.Div([icon_el, html.Span(name, className="module-name")], className="module-title"),
            html.A("Open", href=url, className="btn btn-outline-primary btn-sm")
        ]),
        className="module-card"
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

    header = dbc.Row([
        dbc.Col(html.Div([
            html.H3("SynoviaFusion — Console", className="mb-0"),
            html.Div(f"Welcome, {getattr(current_user, 'display_name', current_user.get_id())} • "
                     f"Role: {getattr(current_user, 'role', 'User')}", className="subhead"),
        ]), md=10),
        dbc.Col(html.Div([
            html.A("Logout", href="/logout", className="btn btn-outline-secondary btn-sm")
        ], className="text-end"), md=2),
    ], className="align-items-center")

    try:
        _profile = fetch_user_profile(user_id)
        kpis = fetch_kpis_for_user(user_id)
        modules = fetch_modules_for_user(user_id)
    except Exception as e:
        return dbc.Container([
            header,
            dbc.Alert(f"Landing page could not load DB data: {type(e).__name__}: {e}", color="danger"),
        ], fluid=True, className="pt-4 pb-5")

    kpi_row = dbc.Row(
        [dbc.Col(kpi_tile(k["title"], k["value"], k.get("hint")), md=3) for k in kpis],
        className="mt-3 g-3"
    )

    module_cards = dbc.Row(
        [dbc.Col(module_card(m["name"], m["url"], m.get("icon")), md=3) for m in modules] or
        [dbc.Col(dbc.Alert("No modules assigned yet. Add rows to ADM.UserModuleAccess.", color="info"), md=12)],
        className="mt-4 g-3"
    )

    return dbc.Container([
        header,
        kpi_row,
        html.H4("Modules", className="mt-4"),
        module_cards,
        html.Hr(),
        html.Div("Tip: each module can connect to its own DB using module-specific env vars (e.g. CORE_DB).", className="footer-tip")
    ], fluid=True, className="pt-4 pb-5")

def create_dash_app(server):
    app = dash.Dash(
        __name__,
        server=server,
        url_base_pathname="/",
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        title="SynoviaFusion Console",
        suppress_callback_exceptions=True
    )
    app.layout = build_layout
    return app
