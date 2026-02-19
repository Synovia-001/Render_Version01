# solas_charts.py
# --------------
# Plotly chart builders + HTML table helpers.

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.io as pio


def fig_to_div(fig: go.Figure) -> str:
    # full_html=False returns just the div+script
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, config={"responsive": True})


def empty_fig(message: str) -> str:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=260, margin=dict(l=20,r=20,t=40,b=20), title="No data")
    return fig_to_div(fig)


def fmt_hours(x: float) -> str:
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return ""


def fmt_pct(x: float) -> str:
    try:
        return f"{float(x)*100:,.1f}%"
    except Exception:
        return ""


def html_table(df: pd.DataFrame, max_rows: int = 500) -> str:
    if df is None or df.empty:
        return '<div class="small">No rows.</div>'

    d = df.head(max_rows).copy()

    # basic formatting for numeric columns
    for c in d.columns:
        if pd.api.types.is_numeric_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else (f"{v:,.2f}" if isinstance(v, (float, np.floating)) else f"{v:,}"))

    return d.to_html(index=False, escape=True, classes="", border=0)


def overview_trend(actual_period: pd.DataFrame, forecast_period: pd.DataFrame,
                   capacity_period: pd.DataFrame, title: str) -> str:
    """
    actual_period columns: period, actual_activity, support, leave
    forecast_period columns: period, forecast
    capacity_period columns: period, capacity, net_capacity
    """
    if actual_period.empty and forecast_period.empty:
        return empty_fig("No data in selected window")

    # align periods
    periods = sorted(set(actual_period.get("period", []).tolist())
                     | set(forecast_period.get("period", []).tolist())
                     | set(capacity_period.get("period", []).tolist()))

    def series(df, col):
        if df.empty:
            return [0.0]*len(periods)
        m = dict(zip(df["period"].astype(str), df[col].astype(float)))
        return [m.get(p, 0.0) for p in periods]

    act = series(actual_period, "actual_activity")
    sup = series(actual_period, "support")
    lev = series(actual_period, "leave")
    fc  = series(forecast_period, "forecast")
    cap = series(capacity_period, "capacity")
    ncap= series(capacity_period, "net_capacity")

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Actual (Activity)", x=periods, y=act))
    fig.add_trace(go.Bar(name="Support", x=periods, y=sup))
    fig.add_trace(go.Bar(name="Leave", x=periods, y=lev))
    fig.add_trace(go.Scatter(name="Forecast (Activity)", x=periods, y=fc, mode="lines+markers"))
    fig.add_trace(go.Scatter(name="Capacity", x=periods, y=cap, mode="lines"))
    fig.add_trace(go.Scatter(name="Net Capacity", x=periods, y=ncap, mode="lines"))
    fig.update_layout(
        barmode="stack",
        title=title,
        xaxis_title="Period",
        yaxis_title="Hours",
        height=420,
        margin=dict(l=20,r=20,t=60,b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig_to_div(fig)


def bar_by_category(df: pd.DataFrame, cat_col: str, val_col: str, title: str, top_n: int = 15) -> str:
    if df.empty:
        return empty_fig("No data")
    g = df.groupby(cat_col, dropna=False)[val_col].sum().sort_values(ascending=False).head(top_n)
    fig = go.Figure(data=[go.Bar(x=g.index.astype(str).tolist(), y=g.values.tolist())])
    fig.update_layout(title=title, xaxis_title=cat_col, yaxis_title="Hours", height=360, margin=dict(l=20,r=20,t=60,b=40))
    return fig_to_div(fig)


def top_resources(actuals: pd.DataFrame, support: pd.DataFrame, title: str, top_n: int = 20) -> str:
    if actuals.empty and support.empty:
        return empty_fig("No data")
    a = actuals.groupby("ResourceLabel")["hours"].sum() if not actuals.empty else pd.Series(dtype=float)
    s = support.groupby("ResourceLabel")["hours_spent"].sum() if not support.empty else pd.Series(dtype=float)
    total = (a.add(s, fill_value=0.0)).sort_values(ascending=False).head(top_n)
    fig = go.Figure(data=[go.Bar(x=total.index.tolist(), y=total.values.tolist())])
    fig.update_layout(title=title, xaxis_title="Resource", yaxis_title="Hours", height=420, margin=dict(l=20,r=20,t=60,b=40))
    return fig_to_div(fig)


def utilisation_by_resource(actuals: pd.DataFrame, support: pd.DataFrame, leave: pd.DataFrame,
                            business_days: int, title: str, top_n: int = 25) -> str:
    if business_days <= 0:
        return empty_fig("No business days in range")
    cap = business_days * 8.0

    a = actuals.groupby("ResourceLabel")["hours"].sum() if not actuals.empty else pd.Series(dtype=float)
    s = support.groupby("ResourceLabel")["hours_spent"].sum() if not support.empty else pd.Series(dtype=float)
    l = leave.groupby("ResourceLabel")["leave_hours"].sum() if not leave.empty else pd.Series(dtype=float)

    work = a.add(s, fill_value=0.0)
    net_cap = pd.Series(cap, index=work.index).sub(l.reindex(work.index).fillna(0.0), fill_value=0.0).replace(0, np.nan)
    util = (work / net_cap).replace([np.inf, -np.inf], np.nan).fillna(0.0).sort_values(ascending=False).head(top_n)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=util.index.tolist(), y=(util.values*100).tolist(), name="Utilisation %"))
    fig.add_trace(go.Scatter(x=util.index.tolist(), y=[100.0]*len(util), mode="lines", name="100%"))
    fig.update_layout(title=title, xaxis_title="Resource", yaxis_title="Utilisation (%)",
                      height=420, margin=dict(l=20,r=20,t=60,b=40))
    return fig_to_div(fig)


def top_activities(actuals: pd.DataFrame, title: str, top_n: int = 25) -> str:
    if actuals.empty:
        return empty_fig("No activity actuals")
    g = actuals.groupby("ActivityLabel")["hours"].sum().sort_values(ascending=False).head(top_n)
    fig = go.Figure(data=[go.Bar(x=g.index.tolist(), y=g.values.tolist())])
    fig.update_layout(title=title, xaxis_title="Activity", yaxis_title="Hours", height=420, margin=dict(l=20,r=20,t=60,b=40))
    return fig_to_div(fig)


def activity_resource_heatmap(actuals: pd.DataFrame, title: str, top_activities: int = 25, top_resources: int = 20) -> str:
    if actuals.empty:
        return empty_fig("No activity actuals")
    mat = pd.pivot_table(actuals, index="ActivityLabel", columns="ResourceLabel", values="hours",
                         aggfunc="sum", fill_value=0.0)
    # reduce size
    act_tot = mat.sum(axis=1).sort_values(ascending=False).head(top_activities).index
    res_tot = mat.sum(axis=0).sort_values(ascending=False).head(top_resources).index
    mat = mat.loc[act_tot, res_tot]

    fig = go.Figure(data=go.Heatmap(
        z=mat.values,
        x=mat.columns.tolist(),
        y=mat.index.tolist(),
        colorbar={"title": "Hours"},
    ))
    fig.update_layout(title=title, xaxis_title="Resource", yaxis_title="Activity",
                      height=520, margin=dict(l=20,r=20,t=60,b=40))
    return fig_to_div(fig)