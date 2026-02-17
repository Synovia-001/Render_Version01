
# -*- coding: utf-8 -*-
"""
DashV2 - Fusion EPOS Production - Interactive Sales Dashboard (Views-based)

- Tabs + tiles + drill-down + heatmap + anomalies + data explorer
- Exports to CSV/Excel (download + saved to disk)
- Uses SQL Server Views created in Fusion_EPOS_Production
- Creates/uses output folder: D:\Dashv2
- Copies logos from D:\Graphics into D:\Dashv2\assets and embeds them in the footer

Run:
  pip install dash dash-bootstrap-components plotly pandas pyodbc openpyxl
  python D:\Dashv2\DashV2_Dashboard.py
Open:
  http://127.0.0.1:8050
"""

from __future__ import annotations

import configparser
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd
import pyodbc

from dash import Dash, dcc, html, dash_table, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go


# ==========================================================
# PATHS / CONFIG
# ==========================================================

# Use raw strings for Windows paths to avoid invalid escape sequence warnings.
INI_PATH = r"D:\Configuration\Fusion_EPOS_Production.ini"
SECTION = "Fusion_EPOS_Production"

OUTDIR = Path(r"D:\Dashv2")
ASSETSDIR = OUTDIR / "assets"
EXPORTDIR = OUTDIR / "exports"
LOGDIR = OUTDIR / "logs"

# Graphics sources (copied into assets/ at startup, if they exist)
FUSION_LOGO_SRC = Path(r"D:\Graphics\FusionLogo.jpg")
BUNNY_IMG_SRC = Path(r"D:\Graphics\RunningBunny.jpg")
SYNOVIA_LOGO_SRC = Path(r"D:\Graphics\SynoviaLogoHor.jpg")


# ==========================================================
# SQL (Views)
# ==========================================================

SQL_STORE_WEEKLY = "SELECT * FROM CUR.vw_StoreWeekly;"
SQL_PRODUCT_WEEKLY = "SELECT * FROM CUR.vw_ProductWeekly;"
SQL_STORE_BASELINES = "SELECT * FROM CUR.vw_StoreBaselines;"
SQL_PRODUCT_BASELINES = "SELECT * FROM CUR.vw_ProductBaselines;"
SQL_LATEST_WEEK = "SELECT * FROM CUR.vw_LatestWeek;"

SQL_STORE_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreAnomalies_4W WHERE CalendarKey = ?;"
SQL_STOREPROD_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductAnomalies_4W WHERE CalendarKey = ?;"
SQL_STOREPROD_WEEKLY_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductWeekly WHERE CalendarKey = ?;"
SQL_STOREPROD_BASELINES_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductBaselines WHERE CalendarKey = ?;"
SQL_WEEKLY_FACT_BY_WEEK = "SELECT * FROM CUR.vw_WeeklySales_Fact WHERE CalendarKey = ?;"


# ==========================================================
# UTIL / CONFIG LOADING
# ==========================================================

@dataclass
class Cfg:
    server: str
    database: str
    user: str
    password: str
    driver: str
    encrypt: str
    trust_server_certificate: str


def ensure_dirs():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    ASSETSDIR.mkdir(parents=True, exist_ok=True)
    EXPORTDIR.mkdir(parents=True, exist_ok=True)
    LOGDIR.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_path = LOGDIR / f"dashv2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    logging.info("Logging initialized.")
    logging.info(f"Log file: {log_path}")


def write_default_css():
    css_path = ASSETSDIR / "dashv2.css"
    if css_path.exists():
        return
    css_path.write_text(
        """
        body { background: #f5f7fb; }
        .kpi-card { border-radius: 14px; }
        .kpi-title { font-size: 12px; color: #6b7280; margin-bottom: 6px; }
        .kpi-value { font-size: 26px; font-weight: 800; color: #111827; }
        .kpi-delta { font-size: 12px; color: #374151; margin-top: 4px; }
        .muted { color: #6b7280; font-size: 12px; }
        .section-title { font-weight: 800; margin: 8px 0 10px 0; }
        .footer-wrap { margin-top: 18px; padding-top: 10px; border-top: 1px solid #e5e7eb; }
        .footer-img { height: 44px; margin-right: 14px; border-radius: 8px; border: 1px solid #e5e7eb; }
        """,
        encoding="utf-8",
    )


def copy_assets():
    """
    Copies local image files into Dash assets folder so they can be embedded in HTML.
    """
    for src in (FUSION_LOGO_SRC, BUNNY_IMG_SRC, SYNOVIA_LOGO_SRC):
        try:
            if src.exists():
                dst = ASSETSDIR / src.name
                if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                    dst.write_bytes(src.read_bytes())
                    logging.info(f"Asset copied: {src} -> {dst}")
            else:
                logging.warning(f"Asset missing (not copied): {src}")
        except Exception:
            logging.exception(f"Failed copying asset: {src}")


def load_cfg() -> Cfg:
    cp = configparser.ConfigParser()
    cp.read(INI_PATH, encoding="utf-8")
    if SECTION not in cp:
        raise RuntimeError(f"INI missing section [{SECTION}] at {INI_PATH}")

    sec = cp[SECTION]
    driver = sec.get("driver", "ODBC Driver 17 for SQL Server").strip()
    encrypt = sec.get("encrypt", "yes").strip()
    tsc = sec.get("trust_server_certificate", "no").strip()

    return Cfg(
        server=sec["server"].strip(),
        database=sec["database"].strip(),
        user=sec["user"].strip(),
        password=sec["password"].strip(),
        driver=driver,
        encrypt=encrypt,
        trust_server_certificate=tsc,
    )


def connect_db(cfg: Cfg):
    conn_str = (
        f"DRIVER={{{cfg.driver}}};"
        f"SERVER={cfg.server};"
        f"DATABASE={cfg.database};"
        f"UID={cfg.user};"
        f"PWD={cfg.password};"
        f"Encrypt={cfg.encrypt};"
        f"TrustServerCertificate={cfg.trust_server_certificate};"
    )
    # NOTE: Dash can run threaded depending on host; to keep it safe,
    # we run the dev server with threaded=False in main().
    return pyodbc.connect(conn_str)


def fmt_int(x: Any) -> str:
    try:
        return f"{int(round(float(x))):,}"
    except Exception:
        return "0"


def fmt_dec(x: Any, p: int = 2) -> str:
    try:
        return f"{float(x):,.{p}f}"
    except Exception:
        return f"{0.0:,.{p}f}"


def pct(a: float, b: float) -> Optional[float]:
    try:
        if b == 0:
            return None
        return (a - b) / b * 100.0
    except Exception:
        return None


def pct_text(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{fmt_dec(v, 1)}%"


def sanitize_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s[:180]


# ==========================================================
# CACHE (prevents hammering SQL on every callback)
# ==========================================================

CACHE: Dict[Tuple[str, Tuple[Any, ...]], Tuple[float, pd.DataFrame]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes

DATA: Dict[str, pd.DataFrame] = {}
LAST_REFRESH: Optional[datetime] = None


def clear_cache():
    CACHE.clear()


def qdf(conn, sql: str, params: Optional[Iterable[Any]] = None, ttl: int = CACHE_TTL_SECONDS) -> pd.DataFrame:
    key = (sql, tuple(params or ()))
    now = time.time()

    if key in CACHE:
        ts, df = CACHE[key]
        if (now - ts) <= ttl:
            return df.copy()

    df = pd.read_sql(sql, conn, params=list(params or []))
    CACHE[key] = (now, df.copy())
    return df


def load_base_frames(conn):
    """
    Base views loaded into memory:
      - latest week
      - store weekly
      - product weekly
      - store baselines
      - product baselines
    Heavy/grain views are queried by week in callbacks.
    """
    global DATA, LAST_REFRESH

    logging.info("Loading base datasets from views...")

    latest = qdf(conn, SQL_LATEST_WEEK, ttl=0)
    store_weekly = qdf(conn, SQL_STORE_WEEKLY, ttl=0)
    product_weekly = qdf(conn, SQL_PRODUCT_WEEKLY, ttl=0)
    store_baselines = qdf(conn, SQL_STORE_BASELINES, ttl=0)
    product_baselines = qdf(conn, SQL_PRODUCT_BASELINES, ttl=0)

    for df in (latest, store_weekly, product_weekly, store_baselines, product_baselines):
        if "Start_Date" in df.columns:
            df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
        if "End_Date" in df.columns:
            df["End_Date"] = pd.to_datetime(df["End_Date"], errors="coerce")
        if "CalendarKey" in df.columns:
            df["CalendarKey"] = df["CalendarKey"].astype(str)

    DATA = {
        "latest": latest,
        "store_weekly": store_weekly,
        "product_weekly": product_weekly,
        "store_baselines": store_baselines,
        "product_baselines": product_baselines,
    }
    LAST_REFRESH = datetime.now()
    logging.info(f"Loaded. store_weekly={len(store_weekly):,} product_weekly={len(product_weekly):,}")


def get_latest_key_fallback() -> Optional[str]:
    latest = DATA.get("latest", pd.DataFrame())
    if latest is not None and not latest.empty and "CalendarKey" in latest.columns:
        return str(latest.iloc[0]["CalendarKey"])
    sw = DATA.get("store_weekly", pd.DataFrame())
    if sw is not None and not sw.empty and "Start_Date" in sw.columns:
        d = sw.dropna(subset=["Start_Date"]).sort_values("Start_Date")
        if not d.empty and "CalendarKey" in d.columns:
            return str(d.iloc[-1]["CalendarKey"])
    return None


def build_week_options() -> list[dict]:
    sw = DATA.get("store_weekly", pd.DataFrame()).copy()
    if sw.empty or "CalendarKey" not in sw.columns or "Start_Date" not in sw.columns:
        return []

    dim = sw.dropna(subset=["Start_Date"]).drop_duplicates(subset=["CalendarKey"]).copy()
    dim = dim.sort_values("Start_Date")

    opts = []
    for _, r in dim.iterrows():
        key = str(r["CalendarKey"])
        sd = r.get("Start_Date", None)
        year = r.get("Dunnes_Year", None)
        week = r.get("Dunnes_Week", None)

        sd_txt = pd.to_datetime(sd).date().isoformat() if pd.notna(sd) else "Unknown"
        if year is not None and week is not None and str(year).strip() != "" and str(week).strip() != "":
            label = f"{int(year)}-W{int(week):02d} ({sd_txt})"
        else:
            label = f"{key} ({sd_txt})"

        opts.append({"label": label, "value": key})
    return opts


def all_stores() -> list[str]:
    sw = DATA.get("store_weekly", pd.DataFrame())
    if sw.empty or "Store_Name" not in sw.columns:
        return []
    return sorted([x for x in sw["Store_Name"].dropna().astype(str).unique().tolist() if x.strip() != ""])


def all_products() -> list[str]:
    pw = DATA.get("product_weekly", pd.DataFrame())
    if pw.empty or "Dynamics_Code" not in pw.columns:
        return []
    return sorted([x for x in pw["Dynamics_Code"].dropna().astype(str).unique().tolist() if x.strip() != ""])


def product_label_map() -> Dict[str, str]:
    pw = DATA.get("product_weekly", pd.DataFrame())
    if pw.empty or "Dynamics_Code" not in pw.columns:
        return {}
    out: Dict[str, str] = {}
    for _, r in pw.dropna(subset=["Dynamics_Code"]).drop_duplicates(subset=["Dynamics_Code"]).iterrows():
        code = str(r["Dynamics_Code"])
        desc = str(r.get("Product_Description", "") or "")
        out[code] = f"{code} — {desc[:60]}" if desc.strip() else code
    return out


# ==========================================================
# KPI + FIGURES
# ==========================================================

def totals_by_week() -> pd.DataFrame:
    sw = DATA.get("store_weekly", pd.DataFrame()).copy()
    if sw.empty:
        return sw
    sw = sw.dropna(subset=["Start_Date"])
    g = sw.groupby(["CalendarKey", "Start_Date"], as_index=False).agg(Units=("Units", "sum"), Value=("Value", "sum"))
    return g.sort_values("Start_Date")


def compute_overview_kpis(selected_key: str) -> Dict[str, Any]:
    tw = totals_by_week()
    if tw.empty:
        return {}

    tw["CalendarKey"] = tw["CalendarKey"].astype(str)
    tw = tw.sort_values("Start_Date")

    cur = tw[tw["CalendarKey"] == str(selected_key)]
    if cur.empty:
        cur = tw.tail(1)

    cur_row = cur.iloc[0]
    cur_units = float(cur_row.get("Units", 0.0))
    cur_value = float(cur_row.get("Value", 0.0))

    # previous week
    tw_idx = tw.reset_index(drop=True)
    pos = tw_idx.index[tw_idx["CalendarKey"] == str(cur_row["CalendarKey"])]
    if len(pos) > 0 and pos[0] > 0:
        prev_row = tw_idx.iloc[pos[0] - 1]
    else:
        prev_row = cur_row

    prev_units = float(prev_row.get("Units", 0.0))
    prev_value = float(prev_row.get("Value", 0.0))

    wow_units_pct = pct(cur_units, prev_units)
    wow_value_pct = pct(cur_value, prev_value)

    # 4W baseline (prior weeks only)
    tw_prior = tw[tw["Start_Date"] < cur_row["Start_Date"]].tail(4)
    base4_units = float(tw_prior["Units"].mean()) if len(tw_prior) else 0.0
    base4_value = float(tw_prior["Value"].mean()) if len(tw_prior) else 0.0

    vs4_units_pct = pct(cur_units, base4_units) if base4_units else None
    vs4_value_pct = pct(cur_value, base4_value) if base4_value else None

    return {
        "cur_units": cur_units,
        "cur_value": cur_value,
        "prev_units": prev_units,
        "prev_value": prev_value,
        "wow_units_pct": wow_units_pct,
        "wow_value_pct": wow_value_pct,
        "base4_units": base4_units,
        "base4_value": base4_value,
        "vs4_units_pct": vs4_units_pct,
        "vs4_value_pct": vs4_value_pct,
        "cur_start": cur_row.get("Start_Date", None),
        "cur_key": str(cur_row.get("CalendarKey", selected_key)),
    }


def fig_total_trend(metric: str, weeks_back: int = 26) -> go.Figure:
    tw = totals_by_week()
    if tw.empty:
        return go.Figure()
    d = tw.dropna(subset=["Start_Date"]).sort_values("Start_Date").tail(int(weeks_back))
    y = "Units" if metric.lower() == "units" else "Value"
    fig = px.line(d, x="Start_Date", y=y, markers=True, title=f"Total Weekly {y} Trend (All Stores)")
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)
    return fig


def fig_top_stores(selected_key: str, top_n: int = 15, metric: str = "Units") -> go.Figure:
    sw = DATA.get("store_weekly", pd.DataFrame()).copy()
    if sw.empty:
        return go.Figure()
    d = sw[sw["CalendarKey"].astype(str) == str(selected_key)].copy()
    if d.empty:
        return go.Figure()
    d = d.groupby("Store_Name", as_index=False).agg(Units=("Units", "sum"), Value=("Value", "sum"))
    d = d.sort_values(metric, ascending=False).head(int(top_n))
    fig = px.bar(d, x=metric, y="Store_Name", orientation="h", title=f"Top Stores by {metric} (Selected Week)")
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=520)
    fig.update_yaxes(categoryorder="total ascending")
    return fig


def fig_top_products(selected_key: str, top_n: int = 15, metric: str = "Units") -> go.Figure:
    pw = DATA.get("product_weekly", pd.DataFrame()).copy()
    if pw.empty:
        return go.Figure()
    d = pw[pw["CalendarKey"].astype(str) == str(selected_key)].copy()
    if d.empty:
        return go.Figure()
    d = d.groupby(["Dynamics_Code", "Product_Description"], as_index=False).agg(Units=("Units", "sum"), Value=("Value", "sum"))
    d = d.sort_values(metric, ascending=False).head(int(top_n))
    d["Product"] = d["Dynamics_Code"].astype(str) + " — " + d["Product_Description"].fillna("").astype(str).str.slice(0, 40)
    fig = px.bar(d, x=metric, y="Product", orientation="h", title=f"Top Products by {metric} (Selected Week)")
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=520)
    fig.update_yaxes(categoryorder="total ascending")
    return fig


def fig_store_trend(store: str, weeks_back: int = 52) -> Tuple[go.Figure, go.Figure]:
    sw = DATA.get("store_weekly", pd.DataFrame()).copy()
    if sw.empty or not store:
        return go.Figure(), go.Figure()
    d = sw[sw["Store_Name"].astype(str) == str(store)].dropna(subset=["Start_Date"]).sort_values("Start_Date").tail(int(weeks_back))
    if d.empty:
        return go.Figure(), go.Figure()
    fig_u = px.line(d, x="Start_Date", y="Units", markers=True, title=f"Store Trend — Units ({store})")
    fig_u.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)
    fig_v = px.line(d, x="Start_Date", y="Value", markers=True, title=f"Store Trend — Value (€) ({store})")
    fig_v.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)
    return fig_u, fig_v


def fig_product_trend(code: str, weeks_back: int = 52) -> Tuple[go.Figure, go.Figure]:
    pw = DATA.get("product_weekly", pd.DataFrame()).copy()
    if pw.empty or not code:
        return go.Figure(), go.Figure()
    d = pw[pw["Dynamics_Code"].astype(str) == str(code)].dropna(subset=["Start_Date"]).sort_values("Start_Date").tail(int(weeks_back))
    if d.empty:
        return go.Figure(), go.Figure()
    title_label = product_label_map().get(str(code), str(code))
    fig_u = px.line(d, x="Start_Date", y="Units", markers=True, title=f"Product Trend — Units ({title_label})")
    fig_u.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)
    fig_v = px.line(d, x="Start_Date", y="Value", markers=True, title=f"Product Trend — Value (€) ({title_label})")
    fig_v.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)
    return fig_u, fig_v


def kpi_card(card_id: str, title: str) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="kpi-title"),
                html.Div("—", id=f"{card_id}-value", className="kpi-value"),
                html.Div("", id=f"{card_id}-delta", className="kpi-delta"),
            ]
        ),
        className="kpi-card",
    )


# ==========================================================
# DASH APP
# ==========================================================

def build_footer() -> dbc.Card:
    """
    Footer with embedded images + the Name/FullName mapping list requested.
    """
    rows = [
        ("FusionLogo.jpg", str(FUSION_LOGO_SRC)),
        ("RunningBunny.jpg", str(BUNNY_IMG_SRC)),
        ("SynoviaLogoHor.jpg", str(SYNOVIA_LOGO_SRC)),
    ]

    mapping_table = dbc.Table(
        [
            html.Thead(html.Tr([html.Th("Name"), html.Th("FullName")])),
            html.Tbody([html.Tr([html.Td(n), html.Td(p)]) for n, p in rows]),
        ],
        bordered=True,
        hover=True,
        size="sm",
        className="mt-2",
        style={"background": "#fff"},
    )

    # Dash assets are served at /assets/<filename>
    imgs = html.Div(
        [
            html.Img(src="/assets/FusionLogo.jpg", className="footer-img"),
            html.Img(src="/assets/RunningBunny.jpg", className="footer-img"),
            html.Img(src="/assets/SynoviaLogoHor.jpg", className="footer-img"),
        ],
        style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"},
    )

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div("Assets (embedded)", className="section-title"),
                html.Div("If an image is missing, ensure it exists in D:\\Graphics or copy it into D:\\Dashv2\\assets.", className="muted"),
                html.Div(className="footer-wrap"),
                imgs,
                mapping_table,
            ]
        ),
        className="mt-3",
    )


def build_app(conn) -> Dash:
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.FLATLY],
        suppress_callback_exceptions=True,
        title="Fusion EPOS — DashV2",
    )

    week_opts = build_week_options()
    default_key = get_latest_key_fallback()

    store_opts = [{"label": s, "value": s} for s in all_stores()]
    prod_map = product_label_map()
    prod_opts = [{"label": prod_map.get(p, p), "value": p} for p in all_products()]

    header = dbc.Row(
        [
            dbc.Col(
                [
                    html.H2("Fusion EPOS — DashV2", style={"margin": "0"}),
                    html.Div("Views-driven dashboard: stores, products, baselines, anomalies, exports.", className="muted"),
                ],
                md=8,
            ),
            dbc.Col(
                [
                    dbc.Button("Refresh from DB", id="btn-refresh", color="primary", className="me-2"),
                    dbc.Badge(id="badge-refresh", color="secondary", className="p-2"),
                ],
                md=4,
                style={"textAlign": "right"},
            ),
        ],
        align="center",
        className="g-2",
    )

    controls = dbc.Card(
        dbc.CardBody(
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Week", className="muted"),
                            dcc.Dropdown(id="dd-week", options=week_opts, value=default_key, clearable=False),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            html.Div("Weeks Back (trend)", className="muted"),
                            dcc.Slider(id="sl-weeks-back", min=8, max=104, step=1, value=26,
                                       tooltip={"placement": "bottom", "always_visible": False}),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            html.Div("Top N", className="muted"),
                            dcc.Slider(id="sl-topn", min=5, max=30, step=1, value=15,
                                       tooltip={"placement": "bottom", "always_visible": False}),
                        ],
                        md=4,
                    ),
                ],
                className="g-3",
            )
        ),
        className="mt-2",
    )

    kpis_row = dbc.Row(
        [
            dbc.Col(kpi_card("kpi-units", "Units (Selected Week)"), md=3),
            dbc.Col(kpi_card("kpi-units-wow", "Units WoW %"), md=3),
            dbc.Col(kpi_card("kpi-units-vs4", "Units vs 4W Baseline %"), md=3),
            dbc.Col(kpi_card("kpi-value", "Value € (Selected Week)"), md=3),
            dbc.Col(kpi_card("kpi-value-wow", "Value € WoW %"), md=3, className="mt-3"),
            dbc.Col(kpi_card("kpi-value-vs4", "Value € vs 4W Baseline %"), md=3, className="mt-3"),
            dbc.Col(kpi_card("kpi-anom-stores", "Store Anomalies (4W)"), md=3, className="mt-3"),
            dbc.Col(kpi_card("kpi-anom-sp", "Store×Product Anomalies (4W)"), md=3, className="mt-3"),
        ],
        className="g-3 mt-1",
    )

    tab_overview = dbc.Container(
        [
            html.Div("Executive Overview", className="section-title"),
            kpis_row,
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="fig-total-units"), md=6, className="mt-3"),
                    dbc.Col(dcc.Graph(id="fig-total-value"), md=6, className="mt-3"),
                ],
                className="g-3",
            ),
            dbc.Row(
                [
                    dbc.Col(dcc.Graph(id="fig-top-stores"), md=6, className="mt-3"),
                    dbc.Col(dcc.Graph(id="fig-top-products"), md=6, className="mt-3"),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tab_stores = dbc.Container(
        [
            html.Div("Stores", className="section-title"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Store", className="muted"),
                            dcc.Dropdown(id="dd-store", options=store_opts, value=None, placeholder="Select a store..."),
                            html.Div("Weeks Back", className="muted mt-2"),
                            dcc.Slider(id="sl-store-weeks", min=8, max=104, step=1, value=52),
                        ],
                        md=4,
                    ),
                    dbc.Col([dcc.Graph(id="fig-store-units"), dcc.Graph(id="fig-store-value")], md=8),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tab_products = dbc.Container(
        [
            html.Div("Products", className="section-title"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Product", className="muted"),
                            dcc.Dropdown(id="dd-product", options=prod_opts, value=None, placeholder="Select a product..."),
                            html.Div("Weeks Back", className="muted mt-2"),
                            dcc.Slider(id="sl-prod-weeks", min=8, max=104, step=1, value=52),
                        ],
                        md=4,
                    ),
                    dbc.Col([dcc.Graph(id="fig-prod-units"), dcc.Graph(id="fig-prod-value")], md=8),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tab_storeprod = dbc.Container(
        [
            html.Div("Store × Product Drill", className="section-title"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Store", className="muted"),
                            dcc.Dropdown(id="dd-sp-store", options=store_opts, value=None, placeholder="Select a store..."),
                            html.Div("Product", className="muted mt-2"),
                            dcc.Dropdown(id="dd-sp-product", options=prod_opts, value=None, placeholder="Select a product..."),
                            html.Div("Show heatmap (Top N stores/products)", className="muted mt-2"),
                            dcc.Slider(id="sl-heat-topn", min=5, max=30, step=1, value=15),
                        ],
                        md=4,
                    ),
                    dbc.Col([dcc.Graph(id="fig-sp-heatmap"), dcc.Graph(id="fig-sp-trend")], md=8),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tab_anoms = dbc.Container(
        [
            html.Div("Anomalies (4W Baseline)", className="section-title"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Threshold (% deviation)", className="muted"),
                            dcc.Slider(id="sl-anom-thresh", min=5, max=80, step=5, value=20),
                            html.Div("Minimum baseline units", className="muted mt-2"),
                            dcc.Slider(id="sl-anom-minbase", min=0, max=50, step=1, value=10),
                            dbc.Button("Download Store×Product anomalies (CSV)", id="btn-dl-anom-csv", color="secondary", className="mt-3"),
                            dbc.Button("Download Store×Product anomalies (Excel)", id="btn-dl-anom-xlsx", color="secondary", className="mt-2"),
                            dcc.Download(id="dl-anom"),
                            html.Div(id="anom-export-msg", className="muted mt-2"),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            dcc.Graph(id="fig-anom-top"),
                            html.Div("Filtered Store×Product anomalies (selected week)", className="muted mt-2"),
                            dash_table.DataTable(
                                id="tbl-anoms",
                                columns=[],
                                data=[],
                                page_size=15,
                                filter_action="native",
                                sort_action="native",
                                export_format="csv",
                                style_table={"overflowX": "auto"},
                                style_cell={"fontFamily": "Segoe UI, Arial", "fontSize": 12, "padding": "6px"},
                                style_header={"fontWeight": "700"},
                            ),
                        ],
                        md=8,
                    ),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tab_data = dbc.Container(
        [
            html.Div("Data Explorer (All Views)", className="section-title"),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Dataset", className="muted"),
                            dcc.Dropdown(
                                id="dd-dataset",
                                options=[
                                    {"label": "Store Weekly (vw_StoreWeekly)", "value": "store_weekly"},
                                    {"label": "Product Weekly (vw_ProductWeekly)", "value": "product_weekly"},
                                    {"label": "Store Baselines (vw_StoreBaselines)", "value": "store_baselines"},
                                    {"label": "Product Baselines (vw_ProductBaselines)", "value": "product_baselines"},
                                    {"label": "Store Anomalies 4W (vw_StoreAnomalies_4W) — filtered by week", "value": "store_anom_by_week"},
                                    {"label": "Store×Product Weekly (vw_StoreProductWeekly) — filtered by week", "value": "storeprod_weekly_by_week"},
                                    {"label": "Store×Product Baselines (vw_StoreProductBaselines) — filtered by week", "value": "storeprod_base_by_week"},
                                    {"label": "Store×Product Anomalies 4W (vw_StoreProductAnomalies_4W) — filtered by week", "value": "storeprod_anom_by_week"},
                                    {"label": "Weekly Sales Fact (vw_WeeklySales_Fact) — filtered by week", "value": "weekly_fact_by_week"},
                                ],
                                value="store_weekly",
                                clearable=False,
                            ),
                            html.Div("Row limit", className="muted mt-2"),
                            dcc.Input(id="inp-rowlimit", type="number", min=100, max=200000, step=100, value=5000, style={"width": "100%"}),
                            dbc.Button("Download (CSV)", id="btn-dl-data-csv", color="secondary", className="mt-3"),
                            dbc.Button("Download (Excel)", id="btn-dl-data-xlsx", color="secondary", className="mt-2"),
                            dcc.Download(id="dl-data"),
                            html.Div(id="data-export-msg", className="muted mt-2"),
                            html.Hr(),
                            html.Div("Notes", className="section-title"),
                            html.Ul(
                                [
                                    html.Li("Heavy views are pulled by selected week to keep it fast."),
                                    html.Li("Table supports filter/sort. Use built-in CSV export too."),
                                    html.Li("Downloads are also saved to D:\\Dashv2\\exports."),
                                ]
                            ),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            html.Div(id="data-rowcount", className="muted"),
                            dash_table.DataTable(
                                id="tbl-data",
                                columns=[],
                                data=[],
                                page_size=20,
                                filter_action="native",
                                sort_action="native",
                                export_format="csv",
                                style_table={"overflowX": "auto"},
                                style_cell={"fontFamily": "Segoe UI, Arial", "fontSize": 12, "padding": "6px"},
                                style_header={"fontWeight": "700"},
                            ),
                        ],
                        md=8,
                    ),
                ],
                className="g-3",
            ),
            dbc.Row([dbc.Col(build_footer(), md=12)], className="g-3"),
        ],
        fluid=True,
        className="p-0",
    )

    tabs = dbc.Tabs(
        [
            dbc.Tab(tab_overview, label="Overview", tab_id="tab-overview"),
            dbc.Tab(tab_stores, label="Stores", tab_id="tab-stores"),
            dbc.Tab(tab_products, label="Products", tab_id="tab-products"),
            dbc.Tab(tab_storeprod, label="Store×Product", tab_id="tab-storeprod"),
            dbc.Tab(tab_anoms, label="Anomalies", tab_id="tab-anoms"),
            dbc.Tab(tab_data, label="Data Explorer", tab_id="tab-data"),
        ],
        id="tabs",
        active_tab="tab-overview",
        className="mt-3",
    )

    app.layout = dbc.Container(
        [
            dcc.Store(id="store-selected-store", data=None),
            dcc.Store(id="store-selected-product", data=None),
            header,
            controls,
            tabs,
            dcc.Interval(id="tick-refresh-badge", interval=30_000, n_intervals=0),
        ],
        fluid=True,
        className="p-3",
    )

    # ======================================================
    # CALLBACKS
    # ======================================================

    @app.callback(Output("badge-refresh", "children"), Input("tick-refresh-badge", "n_intervals"))
    def cb_refresh_badge(_):
        if LAST_REFRESH is None:
            return "Last refresh: never"
        return f"Last refresh: {LAST_REFRESH.strftime('%Y-%m-%d %H:%M:%S')}"

    @app.callback(
        Output("dd-week", "options"),
        Output("dd-week", "value"),
        Input("btn-refresh", "n_clicks"),
        State("dd-week", "value"),
        prevent_initial_call=True,
    )
    def cb_refresh(n_clicks, current_key):
        if not n_clicks:
            return no_update, no_update
        try:
            logging.info("Manual refresh requested.")
            clear_cache()
            load_base_frames(conn)
            opts = build_week_options()
            latest_key = get_latest_key_fallback()
            keep = current_key if current_key and any(o["value"] == current_key for o in opts) else latest_key
            return opts, keep
        except Exception:
            logging.exception("Refresh failed.")
            return no_update, no_update

    @app.callback(
        Output("kpi-units-value", "children"),
        Output("kpi-units-wow-value", "children"),
        Output("kpi-units-vs4-value", "children"),
        Output("kpi-value-value", "children"),
        Output("kpi-value-wow-value", "children"),
        Output("kpi-value-vs4-value", "children"),
        Output("kpi-anom-stores-value", "children"),
        Output("kpi-anom-sp-value", "children"),
        Output("kpi-units-delta", "children"),
        Output("kpi-units-wow-delta", "children"),
        Output("kpi-units-vs4-delta", "children"),
        Output("kpi-value-delta", "children"),
        Output("kpi-value-wow-delta", "children"),
        Output("kpi-value-vs4-delta", "children"),
        Output("kpi-anom-stores-delta", "children"),
        Output("kpi-anom-sp-delta", "children"),
        Output("fig-total-units", "figure"),
        Output("fig-total-value", "figure"),
        Output("fig-top-stores", "figure"),
        Output("fig-top-products", "figure"),
        Input("dd-week", "value"),
        Input("sl-weeks-back", "value"),
        Input("sl-topn", "value"),
    )
    def cb_overview(selected_key, weeks_back, topn):
        if not selected_key:
            return (["—"] * 8) + ([""] * 8) + (go.Figure(), go.Figure(), go.Figure(), go.Figure())

        k = compute_overview_kpis(str(selected_key)) or {}

        # anomaly counts
        try:
            store_anom = qdf(conn, SQL_STORE_ANOM_4W_BY_WEEK, [str(selected_key)])
            store_anom_count = int((store_anom.get("IsUnitsAnomaly_4W", 0) == 1).sum()) if not store_anom.empty else 0
        except Exception:
            store_anom_count = 0

        try:
            sp_anom = qdf(conn, SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(selected_key)])
            sp_anom_count = int((sp_anom.get("IsUnitsAnomaly_4W", 0) == 1).sum()) if not sp_anom.empty else 0
        except Exception:
            sp_anom_count = 0

        units_val = fmt_int(k.get("cur_units", 0))
        value_val = f"€{fmt_dec(k.get('cur_value', 0), 2)}"
        units_wow = pct_text(k.get("wow_units_pct"))
        value_wow = pct_text(k.get("wow_value_pct"))
        units_vs4 = pct_text(k.get("vs4_units_pct"))
        value_vs4 = pct_text(k.get("vs4_value_pct"))

        anom_stores = fmt_int(store_anom_count)
        anom_sp = fmt_int(sp_anom_count)

        d_units = f"Prev: {fmt_int(k.get('prev_units', 0))} | Base4: {fmt_int(k.get('base4_units', 0))}"
        d_value = f"Prev: €{fmt_dec(k.get('prev_value', 0), 2)} | Base4: €{fmt_dec(k.get('base4_value', 0), 2)}"

        fig_u = fig_total_trend("Units", weeks_back=weeks_back)
        fig_v = fig_total_trend("Value", weeks_back=weeks_back)
        fig_ts = fig_top_stores(str(selected_key), top_n=topn, metric="Units")
        fig_tp = fig_top_products(str(selected_key), top_n=topn, metric="Units")

        return (
            units_val, units_wow, units_vs4, value_val, value_wow, value_vs4, anom_stores, anom_sp,
            d_units, "", "", d_value, "", "", "Stores flagged vs 4W", "Store×Product flagged vs 4W",
            fig_u, fig_v, fig_ts, fig_tp
        )

    # Click-to-drill store
    @app.callback(Output("store-selected-store", "data"), Input("fig-top-stores", "clickData"), prevent_initial_call=True)
    def cb_click_store(clickData):
        try:
            if not clickData:
                return no_update
            return clickData["points"][0]["y"]
        except Exception:
            return no_update

    @app.callback(
        Output("dd-store", "value"),
        Output("dd-sp-store", "value"),
        Input("store-selected-store", "data"),
        prevent_initial_call=True,
    )
    def cb_apply_store(store_name):
        if not store_name:
            return no_update, no_update
        return store_name, store_name

    # Click-to-drill product
    @app.callback(Output("store-selected-product", "data"), Input("fig-top-products", "clickData"), prevent_initial_call=True)
    def cb_click_product(clickData):
        try:
            if not clickData:
                return no_update
            y = str(clickData["points"][0]["y"])
            code = y.split("—")[0].strip()
            code = code.split(" ")[0].strip()
            return code
        except Exception:
            return no_update

    @app.callback(
        Output("dd-product", "value"),
        Output("dd-sp-product", "value"),
        Input("store-selected-product", "data"),
        prevent_initial_call=True,
    )
    def cb_apply_product(code):
        if not code:
            return no_update, no_update
        return code, code

    @app.callback(
        Output("fig-store-units", "figure"),
        Output("fig-store-value", "figure"),
        Input("dd-store", "value"),
        Input("sl-store-weeks", "value"),
    )
    def cb_store_figs(store, weeks_back):
        return fig_store_trend(store or "", weeks_back=weeks_back)

    @app.callback(
        Output("fig-prod-units", "figure"),
        Output("fig-prod-value", "figure"),
        Input("dd-product", "value"),
        Input("sl-prod-weeks", "value"),
    )
    def cb_product_figs(code, weeks_back):
        return fig_product_trend(code or "", weeks_back=weeks_back)

    @app.callback(
        Output("fig-sp-heatmap", "figure"),
        Output("fig-sp-trend", "figure"),
        Input("dd-week", "value"),
        Input("dd-sp-store", "value"),
        Input("dd-sp-product", "value"),
        Input("sl-heat-topn", "value"),
    )
    def cb_storeprod(selected_key, store, product, topn):
        if not selected_key:
            return go.Figure(), go.Figure()

        # Heatmap from vw_StoreProductWeekly (selected week)
        try:
            spw = qdf(conn, SQL_STOREPROD_WEEKLY_BY_WEEK, [str(selected_key)])
        except Exception:
            spw = pd.DataFrame()

        if spw.empty:
            heat = go.Figure()
            heat.update_layout(title="No store×product rows for this week.", margin=dict(l=10, r=10, t=45, b=10), height=520)
        else:
            spw["Store_Name"] = spw["Store_Name"].astype(str)
            spw["Dynamics_Code"] = spw["Dynamics_Code"].astype(str)

            top_stores = spw.groupby("Store_Name")["Units"].sum().sort_values(ascending=False).head(int(topn)).index.tolist()
            top_prods = spw.groupby("Dynamics_Code")["Units"].sum().sort_values(ascending=False).head(int(topn)).index.tolist()

            h = spw[spw["Store_Name"].isin(top_stores) & spw["Dynamics_Code"].isin(top_prods)].copy()
            piv = h.pivot_table(index="Store_Name", columns="Dynamics_Code", values="Units", aggfunc="sum", fill_value=0)
            heat = px.imshow(piv, aspect="auto", title="Units Heatmap (Top stores × top products) — Selected Week")
            heat.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=520)

        # Trend for selected store+product (query series)
        if not store or not product:
            trend = go.Figure()
            trend.update_layout(title="Select a store AND a product to see trend.", margin=dict(l=10, r=10, t=45, b=10), height=320)
            return heat, trend

        try:
            sql = """
            SELECT CalendarKey, Start_Date, Store_Name, Dynamics_Code, Product_Description, Units, Value
            FROM CUR.vw_StoreProductWeekly
            WHERE Store_Name = ? AND Dynamics_Code = ?
            ORDER BY Start_Date;
            """
            sp_series = qdf(conn, sql, [store, str(product)], ttl=300)
            sp_series["Start_Date"] = pd.to_datetime(sp_series["Start_Date"], errors="coerce")
            sp_series = sp_series.dropna(subset=["Start_Date"]).sort_values("Start_Date")
        except Exception:
            sp_series = pd.DataFrame()

        if sp_series.empty:
            trend = go.Figure()
            trend.update_layout(title="No data for selected store/product.", margin=dict(l=10, r=10, t=45, b=10), height=320)
        else:
            label = product_label_map().get(str(product), str(product))
            trend = px.line(sp_series, x="Start_Date", y="Units", markers=True, title=f"Store×Product Units Trend — {store} — {label}")
            trend.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=320)

        return heat, trend

    @app.callback(
        Output("tbl-anoms", "columns"),
        Output("tbl-anoms", "data"),
        Output("fig-anom-top", "figure"),
        Input("dd-week", "value"),
        Input("sl-anom-thresh", "value"),
        Input("sl-anom-minbase", "value"),
    )
    def cb_anoms(selected_key, thresh, minbase):
        if not selected_key:
            return [], [], go.Figure()
        try:
            df = qdf(conn, SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(selected_key)])
        except Exception:
            df = pd.DataFrame()

        if df.empty:
            fig = go.Figure()
            fig.update_layout(title="No anomalies for this week.", margin=dict(l=10, r=10, t=45, b=10), height=520)
            return [], [], fig

        if "Units_DevPct_4W" not in df.columns and "Base_Units_4W" in df.columns:
            df["Units_DevPct_4W"] = (df["Units"] - df["Base_Units_4W"]) / df["Base_Units_4W"] * 100.0

        df["Units_DevPct_4W"] = pd.to_numeric(df.get("Units_DevPct_4W", None), errors="coerce")
        df["Base_Units_4W"] = pd.to_numeric(df.get("Base_Units_4W", None), errors="coerce")

        f = df[
            (df["Base_Units_4W"].fillna(0) >= float(minbase)) &
            (df["Units_DevPct_4W"].abs().fillna(0) >= float(thresh))
        ].copy()

        show = f.sort_values("Units_DevPct_4W").head(2000).copy()
        cols = [{"name": c, "id": c} for c in show.columns]
        data = show.to_dict("records")

        movers = f.copy()
        movers["Label"] = movers["Store_Name"].astype(str) + " | " + movers["Dynamics_Code"].astype(str)
        movers = movers.sort_values("Units_DevPct_4W", ascending=True)
        movers = pd.concat([movers.head(12), movers.tail(12)], axis=0).drop_duplicates(subset=["Label"])

        fig = px.bar(movers, x="Units_DevPct_4W", y="Label", orientation="h", title="Biggest movers vs 4W baseline (filtered)")
        fig.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=520)
        fig.update_yaxes(categoryorder="total ascending")

        return cols, data, fig

    def export_to_disk(df: pd.DataFrame, stem: str, ext: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = sanitize_filename(f"{stem}_{ts}.{ext}")
        path = EXPORTDIR / fname
        if ext.lower() == "csv":
            df.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(path, index=False)
        return path

    @app.callback(
        Output("dl-anom", "data"),
        Output("anom-export-msg", "children"),
        Input("btn-dl-anom-csv", "n_clicks"),
        Input("btn-dl-anom-xlsx", "n_clicks"),
        State("dd-week", "value"),
        State("sl-anom-thresh", "value"),
        State("sl-anom-minbase", "value"),
        prevent_initial_call=True,
    )
    def cb_download_anoms(n_csv, n_xlsx, selected_key, thresh, minbase):
        if not selected_key:
            return no_update, "No week selected."
        try:
            df = qdf(conn, SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(selected_key)])
        except Exception:
            df = pd.DataFrame()
        if df.empty:
            return no_update, "No anomaly rows found for this week."

        if "Units_DevPct_4W" not in df.columns and "Base_Units_4W" in df.columns:
            df["Units_DevPct_4W"] = (df["Units"] - df["Base_Units_4W"]) / df["Base_Units_4W"] * 100.0

        df["Units_DevPct_4W"] = pd.to_numeric(df.get("Units_DevPct_4W", None), errors="coerce")
        df["Base_Units_4W"] = pd.to_numeric(df.get("Base_Units_4W", None), errors="coerce")

        f = df[
            (df["Base_Units_4W"].fillna(0) >= float(minbase)) &
            (df["Units_DevPct_4W"].abs().fillna(0) >= float(thresh))
        ].copy()

        trig = ctx.triggered_id
        if trig == "btn-dl-anom-xlsx":
            path = export_to_disk(f, stem=f"anoms_storeprod_week_{selected_key}", ext="xlsx")
            return dcc.send_data_frame(f.to_excel, filename=path.name, index=False), f"Saved: {path}"
        path = export_to_disk(f, stem=f"anoms_storeprod_week_{selected_key}", ext="csv")
        return dcc.send_data_frame(f.to_csv, filename=path.name, index=False, encoding="utf-8-sig"), f"Saved: {path}"

    def load_dataset(dataset: str, selected_key: Optional[str], rowlimit: int) -> pd.DataFrame:
        rowlimit = int(rowlimit or 5000)
        rowlimit = max(100, min(rowlimit, 200000))

        if dataset == "store_weekly":
            return DATA.get("store_weekly", pd.DataFrame()).head(rowlimit).copy()
        if dataset == "product_weekly":
            return DATA.get("product_weekly", pd.DataFrame()).head(rowlimit).copy()
        if dataset == "store_baselines":
            return DATA.get("store_baselines", pd.DataFrame()).head(rowlimit).copy()
        if dataset == "product_baselines":
            return DATA.get("product_baselines", pd.DataFrame()).head(rowlimit).copy()

        if not selected_key:
            return pd.DataFrame()

        if dataset == "store_anom_by_week":
            return qdf(conn, SQL_STORE_ANOM_4W_BY_WEEK, [str(selected_key)]).head(rowlimit).copy()
        if dataset == "storeprod_weekly_by_week":
            return qdf(conn, SQL_STOREPROD_WEEKLY_BY_WEEK, [str(selected_key)]).head(rowlimit).copy()
        if dataset == "storeprod_base_by_week":
            return qdf(conn, SQL_STOREPROD_BASELINES_BY_WEEK, [str(selected_key)]).head(rowlimit).copy()
        if dataset == "storeprod_anom_by_week":
            return qdf(conn, SQL_STOREPROD_ANOM_4W_BY_WEEK, [str(selected_key)]).head(rowlimit).copy()
        if dataset == "weekly_fact_by_week":
            return qdf(conn, SQL_WEEKLY_FACT_BY_WEEK, [str(selected_key)]).head(rowlimit).copy()

        return pd.DataFrame()

    @app.callback(
        Output("tbl-data", "columns"),
        Output("tbl-data", "data"),
        Output("data-rowcount", "children"),
        Input("dd-dataset", "value"),
        Input("dd-week", "value"),
        Input("inp-rowlimit", "value"),
    )
    def cb_data_table(dataset, selected_key, rowlimit):
        df = load_dataset(dataset, selected_key, rowlimit or 5000)
        if df.empty:
            return [], [], "Rows: 0"

        for c in ("Start_Date", "End_Date"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")

        cols = [{"name": c, "id": c} for c in df.columns]
        return cols, df.to_dict("records"), f"Rows shown: {len(df):,}"

    @app.callback(
        Output("dl-data", "data"),
        Output("data-export-msg", "children"),
        Input("btn-dl-data-csv", "n_clicks"),
        Input("btn-dl-data-xlsx", "n_clicks"),
        State("dd-dataset", "value"),
        State("dd-week", "value"),
        State("inp-rowlimit", "value"),
        prevent_initial_call=True,
    )
    def cb_download_data(n_csv, n_xlsx, dataset, selected_key, rowlimit):
        df = load_dataset(dataset, selected_key, rowlimit or 5000)
        if df.empty:
            return no_update, "Nothing to export."

        trig = ctx.triggered_id
        stem = f"export_{dataset}" + (f"_week_{selected_key}" if selected_key else "")

        if trig == "btn-dl-data-xlsx":
            path = export_to_disk(df, stem=stem, ext="xlsx")
            return dcc.send_data_frame(df.to_excel, filename=path.name, index=False), f"Saved: {path}"
        path = export_to_disk(df, stem=stem, ext="csv")
        return dcc.send_data_frame(df.to_csv, filename=path.name, index=False, encoding="utf-8-sig"), f"Saved: {path}"

    return app


# ==========================================================
# MAIN
# ==========================================================

def main():
    ensure_dirs()
    setup_logging()
    write_default_css()
    copy_assets()

    cfg = load_cfg()
    conn = connect_db(cfg)

    clear_cache()
    load_base_frames(conn)

    app = build_app(conn)

    # IMPORTANT:
    # Using a single shared pyodbc connection is safest when Flask isn't threaded.
    # If you later deploy behind a production server with multiple threads/workers,
    # switch qdf() to open a new connection per query (or use SQLAlchemy pooling).
    app.run(host="127.0.0.1", port=8050, debug=False, threaded=False)


if __name__ == "__main__":
    main()
