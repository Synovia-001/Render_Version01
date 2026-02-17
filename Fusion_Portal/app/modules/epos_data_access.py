from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple, Dict

import pandas as pd

from ..config import load_settings
from ..db import get_conn


# ==========================================================
# EPOS DB (module-specific)
# ==========================================================

def _epos_db_name() -> str:
    s = load_settings()
    db = (s.epos_db or "").strip()
    if not db:
        # Do not silently fall back to DB_DATABASE because that is the portal DB.
        raise RuntimeError(
            "EPOS_DB is not configured. Set EPOS_DB in Render env vars to the EPOS database name "
            "(e.g. Fusion_EPOS_Production)."
        )
    return db


def _connect():
    return get_conn(database=_epos_db_name())


# ==========================================================
# SQL (views)
# ==========================================================

# Light-weight helpers (avoid loading huge datasets into memory)
SQL_WEEK_DIM = """
SELECT DISTINCT
    CalendarKey,
    Start_Date,
    End_Date,
    Dunnes_Year,
    Dunnes_Week
FROM CUR.vw_StoreWeekly
ORDER BY Start_Date;
"""

SQL_WEEK_DIM_FALLBACK = """
SELECT DISTINCT
    CalendarKey,
    Start_Date,
    End_Date
FROM CUR.vw_StoreWeekly
ORDER BY Start_Date;
"""

SQL_TOTALS_BY_WEEK = """
SELECT
    CalendarKey,
    Start_Date,
    SUM(Units) AS Units,
    SUM(Value) AS Value
FROM CUR.vw_StoreWeekly
GROUP BY CalendarKey, Start_Date
ORDER BY Start_Date;
"""

SQL_TOP_STORES_BY_WEEK = """
SELECT TOP (?) 
    Store_Name,
    SUM(Units) AS Units,
    SUM(Value) AS Value
FROM CUR.vw_StoreWeekly
WHERE CalendarKey = ?
GROUP BY Store_Name
ORDER BY SUM(Units) DESC;
"""

SQL_TOP_PRODUCTS_BY_WEEK = """
SELECT TOP (?)
    Dynamics_Code,
    MAX(Product_Description) AS Product_Description,
    SUM(Units) AS Units,
    SUM(Value) AS Value
FROM CUR.vw_ProductWeekly
WHERE CalendarKey = ?
GROUP BY Dynamics_Code
ORDER BY SUM(Units) DESC;
"""

SQL_STORE_TREND = """
SELECT
    CalendarKey,
    Start_Date,
    Store_Name,
    Units,
    Value
FROM CUR.vw_StoreWeekly
WHERE Store_Name = ?
ORDER BY Start_Date;
"""

SQL_PRODUCT_TREND = """
SELECT
    CalendarKey,
    Start_Date,
    Dynamics_Code,
    Product_Description,
    Units,
    Value
FROM CUR.vw_ProductWeekly
WHERE Dynamics_Code = ?
ORDER BY Start_Date;
"""

SQL_STORE_LIST = """
SELECT DISTINCT Store_Name
FROM CUR.vw_StoreWeekly
WHERE Store_Name IS NOT NULL
ORDER BY Store_Name;
"""

SQL_PRODUCT_LIST = """
SELECT DISTINCT Dynamics_Code, Product_Description
FROM CUR.vw_ProductWeekly
WHERE Dynamics_Code IS NOT NULL
ORDER BY Dynamics_Code;
"""

SQL_STORE_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreAnomalies_4W WHERE CalendarKey = ?;"
SQL_STOREPROD_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductAnomalies_4W WHERE CalendarKey = ?;"
SQL_STOREPROD_WEEKLY_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductWeekly WHERE CalendarKey = ?;"
SQL_STOREPROD_BASELINES_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductBaselines WHERE CalendarKey = ?;"
SQL_WEEKLY_FACT_BY_WEEK = "SELECT * FROM CUR.vw_WeeklySales_Fact WHERE CalendarKey = ?;"


# ==========================================================
# CACHE
# ==========================================================

CACHE: Dict[Tuple[str, Tuple[Any, ...]], Tuple[float, pd.DataFrame]] = {}
CACHE_TTL_SECONDS = int(os.getenv("EPOS_CACHE_TTL_SECONDS", "900"))  # 15 minutes default

LAST_REFRESH: Optional[datetime] = None


def clear_cache() -> None:
    CACHE.clear()
    global LAST_REFRESH
    LAST_REFRESH = datetime.utcnow()


def qdf(sql: str, params: Optional[Iterable[Any]] = None, ttl: int = CACHE_TTL_SECONDS) -> pd.DataFrame:
    """Query a dataframe with a small in-memory TTL cache.

    Uses a new pooled ODBC connection per call (safe with gunicorn threads/workers).
    """
    key = (sql, tuple(params or ()))
    now = time.time()

    if key in CACHE:
        ts, df = CACHE[key]
        if (now - ts) <= ttl:
            return df.copy()

    with _connect() as conn:
        df = pd.read_sql(sql, conn, params=list(params or []))

    CACHE[key] = (now, df.copy())
    return df


# ==========================================================
# DIMENSIONS / LOOKUPS
# ==========================================================

def week_dim() -> pd.DataFrame:
    """Return week dimension used by dropdown."""
    try:
        df = qdf(SQL_WEEK_DIM, ttl=3600)
    except Exception:
        # Some environments may not have year/week columns exposed
        df = qdf(SQL_WEEK_DIM_FALLBACK, ttl=3600)

    if "Start_Date" in df.columns:
        df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    if "End_Date" in df.columns:
        df["End_Date"] = pd.to_datetime(df["End_Date"], errors="coerce")
    if "CalendarKey" in df.columns:
        df["CalendarKey"] = df["CalendarKey"].astype(str)
    return df


def build_week_options() -> list[dict]:
    df = week_dim()
    if df.empty or "CalendarKey" not in df.columns:
        return []

    df = df.dropna(subset=["Start_Date"]).drop_duplicates(subset=["CalendarKey"]).sort_values("Start_Date")

    opts: list[dict] = []
    for _, r in df.iterrows():
        key = str(r.get("CalendarKey"))
        sd = r.get("Start_Date")
        year = r.get("Dunnes_Year", None)
        week = r.get("Dunnes_Week", None)

        sd_txt = pd.to_datetime(sd).date().isoformat() if pd.notna(sd) else "Unknown"
        if pd.notna(year) and pd.notna(week):
            try:
                label = f"{int(year)}-W{int(week):02d} ({sd_txt})"
            except Exception:
                label = f"{key} ({sd_txt})"
        else:
            label = f"{key} ({sd_txt})"

        opts.append({"label": label, "value": key})

    return opts


def latest_calendar_key() -> Optional[str]:
    df = week_dim()
    if df.empty or "CalendarKey" not in df.columns or "Start_Date" not in df.columns:
        return None
    d = df.dropna(subset=["Start_Date"]).sort_values("Start_Date")
    if d.empty:
        return None
    return str(d.iloc[-1]["CalendarKey"])


def store_options() -> list[dict]:
    df = qdf(SQL_STORE_LIST, ttl=3600)
    if df.empty or "Store_Name" not in df.columns:
        return []
    stores = df["Store_Name"].dropna().astype(str).tolist()
    return [{"label": s, "value": s} for s in stores if s.strip()]


def product_options() -> list[dict]:
    df = qdf(SQL_PRODUCT_LIST, ttl=3600)
    if df.empty or "Dynamics_Code" not in df.columns:
        return []
    df = df.fillna({"Product_Description": ""})
    opts = []
    for _, r in df.iterrows():
        code = str(r.get("Dynamics_Code", "")).strip()
        if not code:
            continue
        desc = str(r.get("Product_Description", "") or "").strip()
        label = f"{code} — {desc[:60]}" if desc else code
        opts.append({"label": label, "value": code})
    return opts


def product_label_map() -> dict[str, str]:
    df = qdf(SQL_PRODUCT_LIST, ttl=3600)
    if df.empty or "Dynamics_Code" not in df.columns:
        return {}
    df = df.fillna({"Product_Description": ""})
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        code = str(r.get("Dynamics_Code", "")).strip()
        if not code:
            continue
        desc = str(r.get("Product_Description", "") or "").strip()
        out[code] = f"{code} — {desc[:60]}" if desc else code
    return out


# ==========================================================
# METRICS
# ==========================================================

def totals_by_week() -> pd.DataFrame:
    df = qdf(SQL_TOTALS_BY_WEEK, ttl=3600)
    if "Start_Date" in df.columns:
        df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    if "CalendarKey" in df.columns:
        df["CalendarKey"] = df["CalendarKey"].astype(str)
    return df.dropna(subset=["Start_Date"]).sort_values("Start_Date")


def _pct(a: float, b: float) -> Optional[float]:
    try:
        if b == 0:
            return None
        return (a - b) / b * 100.0
    except Exception:
        return None


def compute_overview_kpis(selected_key: str) -> dict[str, Any]:
    tw = totals_by_week()
    if tw.empty:
        return {}

    tw = tw.reset_index(drop=True)
    cur = tw[tw["CalendarKey"] == str(selected_key)]
    if cur.empty:
        cur = tw.tail(1)
    cur_row = cur.iloc[0]

    cur_units = float(cur_row.get("Units", 0.0) or 0.0)
    cur_value = float(cur_row.get("Value", 0.0) or 0.0)

    # previous week
    pos = tw.index[tw["CalendarKey"] == str(cur_row["CalendarKey"])].tolist()
    prev_row = tw.iloc[pos[0] - 1] if (pos and pos[0] > 0) else cur_row
    prev_units = float(prev_row.get("Units", 0.0) or 0.0)
    prev_value = float(prev_row.get("Value", 0.0) or 0.0)

    wow_units_pct = _pct(cur_units, prev_units)
    wow_value_pct = _pct(cur_value, prev_value)

    # baseline = mean of prior 4 weeks
    prior = tw[tw["Start_Date"] < cur_row["Start_Date"]].tail(4)
    base4_units = float(prior["Units"].mean()) if len(prior) else 0.0
    base4_value = float(prior["Value"].mean()) if len(prior) else 0.0

    vs4_units_pct = _pct(cur_units, base4_units) if base4_units else None
    vs4_value_pct = _pct(cur_value, base4_value) if base4_value else None

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
