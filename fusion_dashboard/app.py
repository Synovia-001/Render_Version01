import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px

from data_loader import list_available_months, load_month

# ----------------------------
# App
# ----------------------------
app = dash.Dash(__name__)
server = app.server

ROUTE_NOUN = "Route"   # you can rename this later (see naming ideas)

def tile(title: str, value_id: str, hint: str = ""):
    return html.Div(
        className="tile",
        children=[
            html.Div(title, className="k"),
            html.Div("—", id=value_id, className="v"),
            html.Div(hint, className="h"),
        ],
    )

def layout_error(msg: str):
    return html.Div(
        style={"fontFamily":"system-ui","padding":"24px","maxWidth":"980px","margin":"0 auto"},
        children=[
            html.H2("Fusion Dashboard"),
            html.Div("Could not load data."),
            html.Pre(msg, style={"whiteSpace":"pre-wrap","background":"#111827","padding":"12px","borderRadius":"12px"}),
            html.Div("Fix: ensure render.ini is readable locally, and on Render set DB_* environment variables."),
        ],
    )

# ----------------------------
# Startup: load available months
# ----------------------------
try:
    AVAILABLE_MONTHS = list_available_months()
except Exception as e:
    AVAILABLE_MONTHS = []
    STARTUP_ERROR = str(e)
else:
    STARTUP_ERROR = None

if STARTUP_ERROR:
    app.layout = layout_error(STARTUP_ERROR)
else:
    default_month = AVAILABLE_MONTHS[0] if AVAILABLE_MONTHS else None

    app.layout = html.Div(
        className="wrap",
        children=[
            html.H1("Fusion Integration Dashboard"),
            html.Div("Operational view of movements + configured execution steps.", className="muted"),

            html.Div(
                className="controls",
                children=[
                    html.Div(
                        className="control",
                        children=[
                            html.Label("Month"),
                            dcc.Dropdown(
                                id="month",
                                options=[{"label": m, "value": m} for m in AVAILABLE_MONTHS],
                                value=default_month,
                                clearable=False,
                            ),
                        ],
                    ),
                    html.Div(
                        className="control",
                        children=[
                            html.Label("Principal"),
                            dcc.Dropdown(id="principal", clearable=False),
                        ],
                    ),
                    html.Div(
                        className="control",
                        children=[
                            html.Label("Interface"),
                            dcc.Dropdown(id="interface", clearable=False),
                        ],
                    ),
                ],
            ),

            html.Div(
                className="kpis",
                children=[
                    tile("Total movements", "k_total", "In selection"),
                    tile("Success rate", "k_succ", "Higher is better"),
                    tile("Failures", "k_fail", "Count"),
                    tile("Unique runs", "k_runs", "Distinct RunID"),
                    tile("Data moved", "k_gb", "GB total"),
                    tile(f"{ROUTE_NOUN} completion", "k_route", "% COMPLETE runs"),
                    tile(f"Incomplete {ROUTE_NOUN.lower()} runs", "k_incomplete", "Count"),
                ],
            ),

            html.Div(className="grid2", children=[
                html.Div(className="card", children=[html.H3("Movements per day"), dcc.Graph(id="g_daily")]),
                html.Div(className="card", children=[html.H3("Success rate per day"), dcc.Graph(id="g_succdaily")]),
            ]),
            html.Div(className="grid2", children=[
                html.Div(className="card", children=[html.H3("Top interfaces by failures"), dcc.Graph(id="g_topfail")]),
                html.Div(className="card", children=[html.H3("Top error messages"), dcc.Graph(id="g_toperr")]),
            ]),
            html.Div(className="grid2", children=[
                html.Div(className="card", children=[html.H3(f"{ROUTE_NOUN} completion by interface"), dcc.Graph(id="g_route_by_iface")]),
                html.Div(className="card", children=[html.H3("In-progress movements (EndTime is NULL)"), dcc.Graph(id="g_inprogress")]),
            ]),

            html.Div(
                className="note",
                children=[
                    html.Strong("Notes"),
                    html.Div("• If EndTime is NULL, durations can’t be calculated (shown as missing)."),
                    html.Div(f"• {ROUTE_NOUN} completion is based on expected MovementCodes from CFG.Interface_Movements (Active=1)."),
                ],
            )
        ],
    )

# ----------------------------
# Callbacks: principal/interface options
# ----------------------------
@app.callback(
    Output("principal", "options"),
    Output("principal", "value"),
    Input("month", "value"),
)
def update_principal_options(month):
    if not month:
        return [], None

    data = load_month(month)
    run = data["run"]

    if run.empty:
        return [{"label":"(no data)", "value":"__NONE__"}], "__NONE__"

    dim = (
        run.groupby(["Principal_Code"], dropna=False)
           .agg(PrincipalName=("PrincipalName","first"))
           .reset_index()
           .sort_values("PrincipalName")
    )
    opts = [{"label":"All principals", "value":"__ALL__"}] + [
        {"label": f"{r.PrincipalName} ({r.Principal_Code})", "value": r.Principal_Code}
        for r in dim.itertuples(index=False)
    ]
    return opts, "__ALL__"

@app.callback(
    Output("interface", "options"),
    Output("interface", "value"),
    Input("month", "value"),
    Input("principal", "value"),
)
def update_interface_options(month, principal_code):
    if not month:
        return [], None
    data = load_month(month)
    run = data["run"]

    if run.empty or principal_code == "__NONE__":
        return [{"label":"(no data)", "value":"__NONE__"}], "__NONE__"

    d = run if principal_code in (None, "__ALL__") else run[run["Principal_Code"] == principal_code]

    dim = (
        d.groupby(["InterfaceCode"], dropna=False)
         .agg(InterfaceName=("InterfaceName","first"))
         .reset_index()
         .sort_values("InterfaceName")
    )

    opts = [{"label":"All interfaces", "value":"__ALL__"}] + [
        {"label": f"{r.InterfaceName} ({r.InterfaceCode})", "value": r.InterfaceCode}
        for r in dim.itertuples(index=False)
    ]
    return opts, "__ALL__"


# ----------------------------
# Callback: main dashboard
# ----------------------------
@app.callback(
    Output("k_total", "children"),
    Output("k_succ", "children"),
    Output("k_fail", "children"),
    Output("k_runs", "children"),
    Output("k_gb", "children"),
    Output("k_route", "children"),
    Output("k_incomplete", "children"),
    Output("g_daily", "figure"),
    Output("g_succdaily", "figure"),
    Output("g_topfail", "figure"),
    Output("g_toperr", "figure"),
    Output("g_route_by_iface", "figure"),
    Output("g_inprogress", "figure"),
    Input("month", "value"),
    Input("principal", "value"),
    Input("interface", "value"),
)
def update_dashboard(month, principal_code, interface_code):
    empty_fig = px.scatter(pd.DataFrame({"x":[],"y":[]}))

    if not month or principal_code == "__NONE__" or interface_code == "__NONE__":
        return ("0","—","0","0","0 GB","—","0", empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig)

    data = load_month(month)
    run = data["run"]
    completeness = data["completeness"]

    if run.empty:
        return ("0","—","0","0","0 GB","—","0", empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig)

    d = run.copy()
    c = completeness.copy()

    if principal_code not in (None, "__ALL__"):
        d = d[d["Principal_Code"] == principal_code]
        c = c[c["Principal_Code"] == principal_code]

    if interface_code not in (None, "__ALL__"):
        d = d[d["InterfaceCode"] == interface_code]
        c = c[c["InterfaceCode"] == interface_code]

    total = len(d)
    succ_rate = float(d["IsSuccess"].mean() * 100.0) if total else 0.0
    fails = int((~d["IsSuccess"]).sum()) if total else 0
    runs = int(d["RunID"].nunique()) if total else 0
    gb = float(d["FileSizeBytes"].sum() / 1_073_741_824) if total else 0.0

    # Route completion KPIs
    known = c[c["RouteStatus"].isin(["COMPLETE","INCOMPLETE"])]
    if len(known) > 0:
        route_pct = float((known["RouteStatus"] == "COMPLETE").mean() * 100.0)
        incomplete_runs = int((known["RouteStatus"] == "INCOMPLETE").sum())
    else:
        route_pct = None
        incomplete_runs = 0

    # Charts
    daily = d.groupby("StartDate", dropna=False).size().reset_index(name="Movements").sort_values("StartDate")
    fig_daily = px.line(daily, x="StartDate", y="Movements")

    succ = d.groupby("StartDate", dropna=False)["IsSuccess"].mean().reset_index(name="SuccessRate").sort_values("StartDate")
    succ["SuccessRate"] *= 100.0
    fig_succ = px.line(succ, x="StartDate", y="SuccessRate", range_y=[0, 100])

    # Top fail interfaces within selected principal (or all)
    scope = run if principal_code in (None, "__ALL__") else run[run["Principal_Code"] == principal_code]
    topfail = (
        scope.groupby(["InterfaceCode"], dropna=False)["IsSuccess"]
             .apply(lambda s: int((~s).sum()))
             .reset_index(name="Failures")
             .sort_values("Failures", ascending=False)
             .head(12)
    )
    # Add names
    dim_iface = scope.groupby("InterfaceCode").agg(InterfaceName=("InterfaceName","first")).reset_index()
    topfail = topfail.merge(dim_iface, on="InterfaceCode", how="left")
    topfail["InterfaceLabel"] = topfail["InterfaceName"].fillna(topfail["InterfaceCode"]) + " (" + topfail["InterfaceCode"] + ")"
    fig_topfail = px.bar(topfail, x="InterfaceLabel", y="Failures")
    fig_topfail.update_layout(xaxis_title="",)

    err = d[~d["IsSuccess"]].copy()
    toperr = (
        err.groupby("ErrorMessageClean", dropna=False)
           .size()
           .reset_index(name="Count")
           .sort_values("Count", ascending=False)
           .head(12)
    )
    fig_toperr = px.bar(toperr, x="Count", y="ErrorMessageClean", orientation="h")

    # Route completion by interface
    if completeness.empty:
        fig_route = empty_fig
    else:
        cscope = completeness if principal_code in (None, "__ALL__") else completeness[completeness["Principal_Code"] == principal_code]
        known2 = cscope[cscope["RouteStatus"].isin(["COMPLETE","INCOMPLETE"])].copy()
        if known2.empty:
            fig_route = empty_fig
        else:
            agg = known2.groupby(["InterfaceCode"], dropna=False).agg(
                CompleteRate=("RouteStatus", lambda s: float((s == "COMPLETE").mean() * 100.0)),
                Runs=("RunID","count"),
            ).reset_index()
            dim_iface2 = scope.groupby("InterfaceCode").agg(InterfaceName=("InterfaceName","first")).reset_index()
            agg = agg.merge(dim_iface2, on="InterfaceCode", how="left")
            agg["InterfaceLabel"] = agg["InterfaceName"].fillna(agg["InterfaceCode"]) + " (" + agg["InterfaceCode"] + ")"
            agg = agg.sort_values(["CompleteRate","Runs"], ascending=[True, False]).head(15)
            fig_route = px.bar(agg, x="CompleteRate", y="InterfaceLabel", orientation="h")
            fig_route.update_layout(xaxis_title="Completion %", yaxis_title="")

    # In-progress movements
    inprog = d[d["InProgress"]].copy()
    inprog_daily = inprog.groupby("StartDate", dropna=False).size().reset_index(name="InProgress").sort_values("StartDate")
    fig_inprog = px.bar(inprog_daily, x="StartDate", y="InProgress")

    return (
        f"{total:,}",
        f"{succ_rate:.2f}%",
        f"{fails:,}",
        f"{runs:,}",
        f"{gb:.2f} GB",
        "—" if route_pct is None else f"{route_pct:.1f}%",
        f"{incomplete_runs:,}",
        fig_daily,
        fig_succ,
        fig_topfail,
        fig_toperr,
        fig_route,
        fig_inprog,
    )

# ----------------------------
# Styling
# ----------------------------
app.index_string = """
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>Fusion Dashboard</title>
    {%favicon%}
    {%css%}
    <style>
      body{margin:0;background:#0b1220;color:#e8eefc;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;}
      .wrap{max-width:1200px;margin:0 auto;padding:22px 18px 50px;}
      .muted{color:#a9b6d5;margin-bottom:10px;}
      .controls{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:14px 0 10px;}
      .control{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px;}
      .kpis{display:grid;grid-template-columns:repeat(7,1fr);gap:12px;margin:12px 0 12px;}
      .tile{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px;min-height:84px}
      .k{font-size:12px;color:#a9b6d5;margin-bottom:8px}
      .v{font-size:18px;font-weight:800}
      .h{font-size:11px;color:#a9b6d5;margin-top:6px}
      .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
      .card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px}
      .card h3{margin:6px 6px 10px;color:#a9b6d5;font-size:13px}
      .note{margin-top:14px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px;color:#a9b6d5;font-size:12px;line-height:1.6}
      @media(max-width:1180px){.kpis{grid-template-columns:repeat(3,1fr)} .grid2{grid-template-columns:1fr} .controls{grid-template-columns:1fr}}
    </style>
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
"""

if __name__ == "__main__":
    # Dash >=2.17 uses app.run()
    app.run(debug=False)