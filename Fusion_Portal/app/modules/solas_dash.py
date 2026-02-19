"""Fusion Solas module (Dash).

This module is designed to be mounted inside the Fusion Portal Flask server
under /module/Solas/.

It reuses the Solas data helpers (solas_db/solas_transform) and presents a
lightweight, production-safe dashboard:
- Overview KPIs
- Resource utilization
- Activity mix
- Client focus

The dashboard is intentionally defensive: if Solas tables/views are missing in
the target DB/schema, the module renders an informative empty-state rather than
crashing the whole portal.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from ..config import load_settings
from ..data_access import user_can_access_url
from ..db import get_conn

from .solas_db import fetch_dimensions, fetch_facts
from .solas_transform import (
    build_unified_frames,
    compute_activity_mix,
    compute_client_focus,
    compute_overview_metrics,
    compute_resource_utilization,
)


# ---------------------------
# Caching (simple TTL cache)
# ---------------------------

_CACHE_LOCK = Lock()
_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "dims": None,
    "facts": None,
    "frames": None,
}


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("SOLAS_CACHE_TTL_SECONDS", "300"))
    except Exception:
        return 300


def _safe_df(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _load_solas_data(force: bool = False) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    """Load Solas data from DB with a TTL cache.

    Returns (dims, facts, frames).
    - dims/facts are dicts of DataFrames.
    - frames is the output of build_unified_frames.
    """

    now = time.time()
    ttl = _ttl_seconds()

    with _CACHE_LOCK:
        if not force and _CACHE.get("frames") is not None and (now - float(_CACHE.get("ts", 0.0)) < ttl):
            return _CACHE["dims"], _CACHE["facts"], _CACHE["frames"]

    s = load_settings()
    db_name = (s.solas_db or "").strip() or (s.core_db or "").strip()
    schema = (getattr(s, "solas_schema", "dbo") or "dbo").strip() or "dbo"

    if not db_name:
        # No DB configured – return empty but don't crash.
        dims: Dict[str, pd.DataFrame] = {}
        facts: Dict[str, pd.DataFrame] = {}
        frames: Dict[str, pd.DataFrame] = {}
        with _CACHE_LOCK:
            _CACHE.update({"ts": now, "dims": dims, "facts": facts, "frames": frames})
        return dims, facts, frames

    try:
        with get_conn(database=db_name) as conn:
            dims = fetch_dimensions(conn, schema=schema)
            facts = fetch_facts(conn, schema=schema)
        frames = build_unified_frames(dims, facts)
    except Exception:
        # Degrade gracefully.
        dims = {}
        facts = {}
        frames = {}

    with _CACHE_LOCK:
        _CACHE.update({"ts": now, "dims": dims, "facts": facts, "frames": frames})

    return dims, facts, frames


# ---------------------------
# UI helpers
# ---------------------------


def _asset_img(asset_url, filename: str, alt: str, height: int = 34, style: Optional[dict] = None):
    return html.Img(
        src=asset_url(filename),
        alt=alt,
        style={"height": f"{height}px", **(style or {})},
    )


def _kpi_card(title: str, value: str, subtitle: str = "", icon: str = "bi bi-graph-up"):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(title, className="kpi-title"),
                                html.Div(value, className="kpi-value"),
                                html.Div(subtitle, className="kpi-subtitle") if subtitle else None,
                            ],
                            className="kpi-text",
                        ),
                        html.I(className=icon + " kpi-icon"),
                    ],
                    className="kpi-row",
                )
            ]
        ),
        className="kpi-card",
    )


def _empty_state(message: str):
    return dbc.Alert(
        [
            html.H5("Fusion Solas"),
            html.Div(message),
            html.Hr(),
            html.Div(
                "Tip: set SOLAS_DB (and optionally SOLAS_SCHEMA) in Render env vars to enable Solas data.",
                className="text-muted",
            ),
        ],
        color="warning",
        className="mt-3",
    )


@dataclass
class _SolasSnapshot:
    frames: Dict[str, pd.DataFrame]
    metrics: Dict[str, Any]
    res_util: pd.DataFrame
    act_mix: pd.DataFrame
    cli_focus: pd.DataFrame


def _build_snapshot(frames: Dict[str, pd.DataFrame]) -> _SolasSnapshot:
    # Defensive: each compute_* handles empty frames, but we'll ensure dict keys exist.
    f = {k: _safe_df(v) for k, v in (frames or {}).items()}

    metrics = compute_overview_metrics(f)
    res_util = compute_resource_utilization(f)
    act_mix = compute_activity_mix(f)
    cli_focus = compute_client_focus(f)

    # Coerce to DataFrames
    res_util = _safe_df(res_util)
    act_mix = _safe_df(act_mix)
    cli_focus = _safe_df(cli_focus)

    return _SolasSnapshot(frames=f, metrics=metrics, res_util=res_util, act_mix=act_mix, cli_focus=cli_focus)


def _to_date_range(frames: Dict[str, pd.DataFrame]) -> Tuple[Optional[str], Optional[str]]:
    # Determine min/max date from any available frame.
    dates = []
    for key in ("actuals", "support", "leave", "forecasts"):
        df = _safe_df((frames or {}).get(key))
        if df.empty:
            continue
        if "Date" in df.columns:
            s = pd.to_datetime(df["Date"], errors="coerce")
            if s.notna().any():
                dates.append(s.min())
                dates.append(s.max())
    if not dates:
        return None, None
    mn = min(dates)
    mx = max(dates)
    if pd.isna(mn) or pd.isna(mx):
        return None, None
    return mn.date().isoformat(), mx.date().isoformat()


# ---------------------------
# Main layout
# ---------------------------


def build_layout(asset_url):
    dims, facts, frames = _load_solas_data(force=False)

    # Access check is handled by create_solas_dash_app (needs request context for current_user),
    # but we still build a safe layout here.

    if not frames or all(_safe_df(frames.get(k)).empty for k in ("actuals", "support", "leave", "forecasts")):
        return dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(_asset_img(asset_url, "FusionLogo.jpg", "Fusion", height=40), width="auto"),
                        dbc.Col(html.H3("Fusion Solas"), className="d-flex align-items-center"),
                    ],
                    className="mt-3",
                    align="center",
                ),
                _empty_state(
                    "No Solas data was found (or the module is not configured yet). "
                    "This module expects Solas tables/views in the SOLAS_DB database."
                ),
            ],
            fluid=True,
        )

    snap = _build_snapshot(frames)
    min_date, max_date = _to_date_range(frames)

    # KPI values (safe formatting)
    def fmt(v, default="-"):
        if v is None:
            return default
        try:
            if isinstance(v, float):
                return f"{v:,.2f}"
            return str(v)
        except Exception:
            return default

    kpi_cards = dbc.Row(
        [
            dbc.Col(_kpi_card("Actual Hours", fmt(snap.metrics.get("actual_hours")), "Time booked", icon="bi bi-clock"), md=3),
            dbc.Col(_kpi_card("Support Hours", fmt(snap.metrics.get("support_hours")), "Ops / support", icon="bi bi-headset"), md=3),
            dbc.Col(_kpi_card("Leave Hours", fmt(snap.metrics.get("leave_hours")), "Planned/recorded", icon="bi bi-calendar2-week"), md=3),
            dbc.Col(_kpi_card("Utilisation", fmt(snap.metrics.get("utilisation_pct")), "% of capacity", icon="bi bi-speedometer2"), md=3),
        ],
        className="g-3 mt-2",
    )

    # Overview charts
    actuals = _safe_df(snap.frames.get("actuals"))
    forecasts = _safe_df(snap.frames.get("forecasts"))

    # Build a daily rollup for charts
    daily = pd.DataFrame()
    if not actuals.empty and {"Date", "Hours"}.issubset(set(actuals.columns)):
        daily = actuals.groupby("Date", as_index=False)["Hours"].sum().rename(columns={"Hours": "Actual Hours"})
    if not forecasts.empty and {"Date", "ForecastHours"}.issubset(set(forecasts.columns)):
        f2 = forecasts.groupby("Date", as_index=False)["ForecastHours"].sum().rename(columns={"ForecastHours": "Forecast Hours"})
        daily = daily.merge(f2, on="Date", how="outer") if not daily.empty else f2

    if not daily.empty and "Date" in daily.columns:
        daily["Date"] = pd.to_datetime(daily["Date"], errors="coerce")
        daily = daily.sort_values("Date")

    fig_trend = px.line(daily, x="Date", y=[c for c in daily.columns if c != "Date"], markers=True) if not daily.empty else px.line()
    fig_trend.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")

    # Resource utilisation bar
    util_df = snap.res_util
    fig_util = px.bar()
    if not util_df.empty and {"Resource", "UtilisationPct"}.issubset(util_df.columns):
        util_df2 = util_df.sort_values("UtilisationPct", ascending=False).head(20)
        fig_util = px.bar(util_df2, x="UtilisationPct", y="Resource", orientation="h")
        fig_util.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="")

    # Activity mix
    mix_df = snap.act_mix
    fig_mix = px.pie()
    if not mix_df.empty and {"Activity", "Hours"}.issubset(mix_df.columns):
        fig_mix = px.pie(mix_df, names="Activity", values="Hours", hole=0.4)
        fig_mix.update_layout(margin=dict(l=10, r=10, t=30, b=10))

    # Client focus
    cf_df = snap.cli_focus
    fig_cf = px.bar()
    if not cf_df.empty and {"Client", "Hours"}.issubset(cf_df.columns):
        cf2 = cf_df.sort_values("Hours", ascending=False).head(15)
        fig_cf = px.bar(cf2, x="Hours", y="Client", orientation="h")
        fig_cf.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="")

    controls = dbc.Row(
        [
            dbc.Col(
                [
                    html.Div("Date range", className="filter-label"),
                    dcc.DatePickerRange(
                        id="solas-date-range",
                        min_date_allowed=min_date,
                        max_date_allowed=max_date,
                        start_date=min_date,
                        end_date=max_date,
                        display_format="YYYY-MM-DD",
                    ),
                ],
                md=6,
            ),
            dbc.Col(
                [
                    html.Div("Cache", className="filter-label"),
                    dbc.Button("Refresh data", id="solas-refresh", color="secondary", outline=True, className="w-100"),
                ],
                md=3,
            ),
            dbc.Col(
                [
                    html.Div("Export", className="filter-label"),
                    dbc.Button("Download CSV", id="solas-download-btn", color="primary", className="w-100"),
                    dcc.Download(id="solas-download"),
                ],
                md=3,
            ),
        ],
        className="g-3 mt-2",
        align="end",
    )

    tabs = dcc.Tabs(
        id="solas-tabs",
        value="tab-overview",
        children=[
            dcc.Tab(label="Overview", value="tab-overview"),
            dcc.Tab(label="Resources", value="tab-resources"),
            dcc.Tab(label="Activities", value="tab-activities"),
            dcc.Tab(label="Clients", value="tab-clients"),
        ],
        className="mt-3",
    )

    content = html.Div(id="solas-tab-content", className="mt-3")

    footer = html.Div(
        [
            html.Hr(),
            html.Div(
                [
                    _asset_img(asset_url, "SynoviaLogoHor.jpg", "Synovia", height=36, style={"opacity": 0.9}),
                ],
                className="d-flex justify-content-center",
            ),
            html.Div("Fusion Solas • Operational analytics", className="text-center text-muted mt-2", style={"fontSize": "0.85rem"}),
        ],
        className="mt-4",
    )

    # Store snapshot in hidden dcc.Store for reuse in callbacks (lightweight summary only)
    store_payload = {
        "has_data": True,
        "min_date": min_date,
        "max_date": max_date,
    }

    return dbc.Container(
        [
            dcc.Store(id="solas-meta", data=store_payload),
            dbc.Row(
                [
                    dbc.Col(_asset_img(asset_url, "FusionLogo.jpg", "Fusion", height=44), width="auto"),
                    dbc.Col(html.Div([html.H3("Fusion Solas"), html.Div("Capacity • Utilisation • Focus", className="text-muted")]), className="d-flex align-items-center"),
                ],
                className="mt-3",
                align="center",
            ),
            controls,
            kpi_cards,
            tabs,
            content,
            footer,
        ],
        fluid=True,
        className="fusion-page",
    )


def _filter_by_date(df: pd.DataFrame, start_date: Optional[str], end_date: Optional[str]) -> pd.DataFrame:
    if df.empty or "Date" not in df.columns:
        return df
    s = pd.to_datetime(start_date, errors="coerce") if start_date else None
    e = pd.to_datetime(end_date, errors="coerce") if end_date else None
    d = df.copy()
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    if s is not None and pd.notna(s):
        d = d[d["Date"] >= s]
    if e is not None and pd.notna(e):
        d = d[d["Date"] <= e]
    return d


def create_solas_dash_app(server, url_base_pathname: str = "/module/Solas/"):
    """Attach the Solas Dash app to the provided Flask server."""

    base_url = url_base_pathname.rstrip("/")

    def _asset_url(filename: str) -> str:
        # All Dash apps in this portal use the same /assets mount.
        return f"/assets/{filename}"

    app = Dash(
        __name__,
        server=server,
        url_base_pathname=url_base_pathname,
        requests_pathname_prefix=url_base_pathname,
        suppress_callback_exceptions=True,
        title="Fusion Solas",
        external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
        assets_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "assets"),
        assets_url_path="/assets",
    )

    # Permission gate: if user can't access, render a simple message.
    def layout():
        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return dbc.Container([_empty_state("Please sign in to view this module.")], fluid=True)
            alt_urls = ['/module/Fusion_Solas', '/module/solas', '/module/SOLAS']
            allowed = user_can_access_url(current_user.id, base_url) or any(user_can_access_url(current_user.id, u) for u in alt_urls)
            if not allowed:
                return dbc.Container(
                    [dbc.Alert("You do not have access to the Solas module.", color="danger")],
                    fluid=True,
                )
        except Exception:
            # If anything about current_user fails, still show a safe message.
            return dbc.Container([_empty_state("Unable to validate user session.")], fluid=True)

        return build_layout(_asset_url)

    app.layout = layout

    @app.callback(
        Output("solas-tab-content", "children"),
        Input("solas-tabs", "value"),
        Input("solas-date-range", "start_date"),
        Input("solas-date-range", "end_date"),
        Input("solas-refresh", "n_clicks"),
    )
    def render_tab(tab, start_date, end_date, n_refresh):
        # refresh triggers cache bust
        force = bool(n_refresh)
        _, _, frames = _load_solas_data(force=force)
        if not frames:
            return _empty_state("No Solas frames available.")

        # Build snapshot post-filter (keeps it consistent for charts/tables)
        f = {k: _filter_by_date(_safe_df(v), start_date, end_date) for k, v in frames.items()}
        snap = _build_snapshot(f)

        if tab == "tab-resources":
            util_df = snap.res_util
            if util_df.empty:
                return _empty_state("No resource utilisation data.")
            fig = px.bar(util_df.sort_values("UtilisationPct", ascending=False).head(30), x="UtilisationPct", y="Resource", orientation="h")
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="")
            return dbc.Row(
                [
                    dbc.Col(dcc.Graph(figure=fig), md=7),
                    dbc.Col(
                        dbc.Table.from_dataframe(util_df.head(30), striped=True, bordered=True, hover=True, size="sm"),
                        md=5,
                        style={"maxHeight": "70vh", "overflowY": "auto"},
                    ),
                ],
                className="g-3",
            )

        if tab == "tab-activities":
            mix_df = snap.act_mix
            if mix_df.empty:
                return _empty_state("No activity mix data.")
            fig = px.pie(mix_df, names="Activity", values="Hours", hole=0.4)
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
            return dbc.Row(
                [
                    dbc.Col(dcc.Graph(figure=fig), md=6),
                    dbc.Col(
                        dbc.Table.from_dataframe(mix_df.head(50), striped=True, bordered=True, hover=True, size="sm"),
                        md=6,
                        style={"maxHeight": "70vh", "overflowY": "auto"},
                    ),
                ],
                className="g-3",
            )

        if tab == "tab-clients":
            cf_df = snap.cli_focus
            if cf_df.empty:
                return _empty_state("No client focus data.")
            fig = px.bar(cf_df.sort_values("Hours", ascending=False).head(20), x="Hours", y="Client", orientation="h")
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="")
            return dbc.Row(
                [
                    dbc.Col(dcc.Graph(figure=fig), md=7),
                    dbc.Col(
                        dbc.Table.from_dataframe(cf_df.head(30), striped=True, bordered=True, hover=True, size="sm"),
                        md=5,
                        style={"maxHeight": "70vh", "overflowY": "auto"},
                    ),
                ],
                className="g-3",
            )

        # Overview default
        # Trend chart built from filtered frames
        actuals = _safe_df(snap.frames.get("actuals"))
        forecasts = _safe_df(snap.frames.get("forecasts"))
        daily = pd.DataFrame()
        if not actuals.empty and {"Date", "Hours"}.issubset(set(actuals.columns)):
            daily = actuals.groupby("Date", as_index=False)["Hours"].sum().rename(columns={"Hours": "Actual Hours"})
        if not forecasts.empty and {"Date", "ForecastHours"}.issubset(set(forecasts.columns)):
            f2 = forecasts.groupby("Date", as_index=False)["ForecastHours"].sum().rename(columns={"ForecastHours": "Forecast Hours"})
            daily = daily.merge(f2, on="Date", how="outer") if not daily.empty else f2
        if not daily.empty and "Date" in daily.columns:
            daily["Date"] = pd.to_datetime(daily["Date"], errors="coerce")
            daily = daily.sort_values("Date")

        fig_trend = px.line(daily, x="Date", y=[c for c in daily.columns if c != "Date"], markers=True) if not daily.empty else px.line()
        fig_trend.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")

        # utilization chart (top 15)
        util_df = snap.res_util
        fig_util = px.bar()
        if not util_df.empty and {"Resource", "UtilisationPct"}.issubset(util_df.columns):
            fig_util = px.bar(util_df.sort_values("UtilisationPct", ascending=False).head(15), x="UtilisationPct", y="Resource", orientation="h")
            fig_util.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title="")

        return dbc.Row(
            [
                dbc.Col(dcc.Graph(figure=fig_trend), md=7),
                dbc.Col(dcc.Graph(figure=fig_util), md=5),
            ],
            className="g-3",
        )

    @app.callback(
        Output("solas-download", "data"),
        Input("solas-download-btn", "n_clicks"),
        State("solas-tabs", "value"),
        State("solas-date-range", "start_date"),
        State("solas-date-range", "end_date"),
        prevent_initial_call=True,
    )
    def download_csv(n, tab, start_date, end_date):
        if not n:
            raise PreventUpdate
        _, _, frames = _load_solas_data(force=False)
        f = {k: _filter_by_date(_safe_df(v), start_date, end_date) for k, v in frames.items()}
        snap = _build_snapshot(f)
        if tab == "tab-resources":
            df = snap.res_util
            filename = "solas_resources.csv"
        elif tab == "tab-activities":
            df = snap.act_mix
            filename = "solas_activities.csv"
        elif tab == "tab-clients":
            df = snap.cli_focus
            filename = "solas_clients.csv"
        else:
            # Export daily rollup
            actuals = _safe_df(snap.frames.get("actuals"))
            daily = pd.DataFrame()
            if not actuals.empty and {"Date", "Hours"}.issubset(set(actuals.columns)):
                daily = actuals.groupby("Date", as_index=False)["Hours"].sum().rename(columns={"Hours": "Actual Hours"})
            df = daily
            filename = "solas_overview_daily.csv"

        return dcc.send_data_frame(df.to_csv, filename, index=False)

    return app
