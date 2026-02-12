import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px

from data_loader import load_data
from config import load_settings

app = dash.Dash(__name__)
server = app.server

def kpi_card(title: str, value_id: str, sub: str = ""):
    return html.Div(
        className="tile",
        children=[
            html.Div(title, className="k"),
            html.Div("—", id=value_id, className="v"),
            html.Div(sub, className="h") if sub else html.Div("", className="h"),
        ],
    )

# Load once on startup (simple + stable). Later we can add refresh/caching.
settings = load_settings()
REPORT_MONTH = settings.get("REPORT_MONTH", "2025-01")

try:
    DF = load_data()
except Exception as e:
    DF = pd.DataFrame()
    LOAD_ERROR = str(e)
else:
    LOAD_ERROR = None

if DF.empty:
    app.layout = html.Div(
        style={"fontFamily": "system-ui", "padding": "24px"},
        children=[
            html.H2("Fusion Dashboard"),
            html.Div("Could not load data." if LOAD_ERROR else "No data returned for this month."),
            html.Pre(LOAD_ERROR or "", style={"whiteSpace": "pre-wrap"}),
            html.Div("Fix: set DB_* env vars on Render, or render.ini locally."),
        ],
    )
else:
    principals = ["All"] + sorted(DF["Principal_Code"].dropna().unique().tolist())

    def interfaces_for(principal: str):
        d = DF if principal == "All" else DF[DF["Principal_Code"] == principal]
        vals = sorted(d["InterfaceCode"].dropna().unique().tolist())
        return ["All"] + vals

    app.layout = html.Div(
        className="wrap",
        children=[
            html.H1("Fusion Integration Dashboard"),
            html.Div(f"Month: {REPORT_MONTH}", className="muted"),

            html.Div(
                className="controls",
                children=[
                    html.Div(
                        className="control",
                        children=[
                            html.Label("Principal"),
                            dcc.Dropdown(
                                id="principal",
                                options=[{"label": p, "value": p} for p in principals],
                                value="All",
                                clearable=False,
                            ),
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
                    kpi_card("Total movements", "k_total", "In selection"),
                    kpi_card("Success rate", "k_succ", "Higher is better"),
                    kpi_card("Failures", "k_fail", "Count"),
                    kpi_card("Unique runs", "k_runs", "Distinct RunID"),
                    kpi_card("Data moved", "k_gb", "GB total"),
                    kpi_card("Avg duration", "k_avgdur", "Seconds"),
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
        ],
    )

    @app.callback(
        Output("interface", "options"),
        Output("interface", "value"),
        Input("principal", "value"),
    )
    def update_interface_options(principal):
        opts = interfaces_for(principal)
        return ([{"label": x, "value": x} for x in opts], "All")

    @app.callback(
        Output("k_total", "children"),
        Output("k_succ", "children"),
        Output("k_fail", "children"),
        Output("k_runs", "children"),
        Output("k_gb", "children"),
        Output("k_avgdur", "children"),
        Output("g_daily", "figure"),
        Output("g_succdaily", "figure"),
        Output("g_topfail", "figure"),
        Output("g_toperr", "figure"),
        Input("principal", "value"),
        Input("interface", "value"),
    )
    def update_dash(principal, interface):
        d = DF.copy()
        if principal != "All":
            d = d[d["Principal_Code"] == principal]
        if interface != "All":
            d = d[d["InterfaceCode"] == interface]

        total = len(d)
        succ_rate = float(d["IsSuccess"].mean() * 100.0) if total else 0.0
        fails = int((~d["IsSuccess"]).sum()) if total else 0
        runs = int(d["RunID"].nunique()) if total else 0
        gb = float(d["FileSizeBytes"].sum() / 1_073_741_824) if total else 0.0
        avgdur = float(d["DurationSeconds"].mean()) if d["DurationSeconds"].notna().any() else None

        daily = d.groupby("StartDate", dropna=False).size().reset_index(name="Movements").sort_values("StartDate")
        fig_daily = px.line(daily, x="StartDate", y="Movements")

        succ = d.groupby("StartDate", dropna=False)["IsSuccess"].mean().reset_index(name="SuccessRate").sort_values("StartDate")
        succ["SuccessRate"] *= 100.0
        fig_succ = px.line(succ, x="StartDate", y="SuccessRate", range_y=[0, 100])

        by_iface = DF if principal == "All" else DF[DF["Principal_Code"] == principal]
        topfail = (
            by_iface.groupby("InterfaceCode", dropna=False)["IsSuccess"]
            .apply(lambda s: int((~s).sum()))
            .reset_index(name="Failures")
            .sort_values("Failures", ascending=False)
            .head(12)
        )
        fig_topfail = px.bar(topfail, x="InterfaceCode", y="Failures")

        err = d[~d["IsSuccess"]].copy()
        toperr = (
            err.groupby("ErrorMessageClean", dropna=False)
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
            .head(12)
        )
        fig_toperr = px.bar(toperr, x="Count", y="ErrorMessageClean", orientation="h")

        return (
            f"{total:,}",
            f"{succ_rate:.2f}%",
            f"{fails:,}",
            f"{runs:,}",
            f"{gb:.2f} GB",
            "—" if avgdur is None else f"{avgdur:,.1f}s",
            fig_daily,
            fig_succ,
            fig_topfail,
            fig_toperr,
        )

# Minimal styling (keeps it clean on Render)
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
      .muted{color:#a9b6d5;margin-bottom:14px;}
      .controls{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0 10px;}
      .control{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px;}
      .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:12px 0 12px;}
      .tile{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:12px;min-height:84px}
      .k{font-size:12px;color:#a9b6d5;margin-bottom:8px}
      .v{font-size:18px;font-weight:800}
      .h{font-size:11px;color:#a9b6d5;margin-top:6px}
      .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
      .card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px}
      .card h3{margin:6px 6px 10px;color:#a9b6d5;font-size:13px}
      @media(max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)} .grid2{grid-template-columns:1fr} .controls{grid-template-columns:1fr}}
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
    app.run(debug=False)
