from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd

from ..config import load_settings
from ..db import get_conn

_CACHE: Dict[Tuple[str, Tuple[Any, ...]], Tuple[float, pd.DataFrame]] = {}
DEFAULT_TTL_SECONDS = 300

def _epos_db() -> str:
    s = load_settings()
    if not s.epos_db:
        raise RuntimeError("EPOS_DB (or Epos_DB) environment variable is not set.")
    return s.epos_db

def qdf(sql: str, params: Optional[Iterable[Any]] = None, ttl: int = DEFAULT_TTL_SECONDS) -> pd.DataFrame:
    key = (sql, tuple(params or ()))
    now = time.time()
    if ttl > 0 and key in _CACHE:
        ts, df = _CACHE[key]
        if (now - ts) <= ttl:
            return df.copy()

    with get_conn(database=_epos_db()) as conn:
        df = pd.read_sql(sql, conn, params=list(params or []))

    _CACHE[key] = (now, df.copy())
    return df

def clear_cache() -> None:
    _CACHE.clear()

SQL_LATEST_WEEK = "SELECT * FROM CUR.vw_LatestWeek;"
SQL_STORE_WEEKLY = "SELECT * FROM CUR.vw_StoreWeekly;"
SQL_PRODUCT_WEEKLY = "SELECT * FROM CUR.vw_ProductWeekly;"
SQL_STOREPROD_WEEKLY_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductWeekly WHERE CalendarKey = ?;"
SQL_STOREPROD_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreProductAnomalies_4W WHERE CalendarKey = ?;"
SQL_STORE_ANOM_4W_BY_WEEK = "SELECT * FROM CUR.vw_StoreAnomalies_4W WHERE CalendarKey = ?;"

SQL_STORE_WEEKLY_BY_STORE = "SELECT * FROM CUR.vw_StoreWeekly WHERE Store_Name = ? ORDER BY Start_Date;"
SQL_PRODUCT_WEEKLY_BY_CODE = "SELECT * FROM CUR.vw_ProductWeekly WHERE Dynamics_Code = ? ORDER BY Start_Date;"

SQL_STOREPROD_WEEKLY_BY_WEEK_STORE = "SELECT * FROM CUR.vw_StoreProductWeekly WHERE CalendarKey = ? AND Store_Name = ?;"
SQL_STOREPROD_WEEKLY_BY_WEEK_PRODUCT = "SELECT * FROM CUR.vw_StoreProductWeekly WHERE CalendarKey = ? AND Dynamics_Code = ?;"

SQL_STOREPROD_HISTORY = "SELECT TOP (104) * FROM CUR.vw_StoreProductWeekly WHERE Store_Name = ? AND Dynamics_Code = ? ORDER BY Start_Date DESC;"

@dataclass
class EposBase:
    latest: pd.DataFrame
    store_weekly: pd.DataFrame
    product_weekly: pd.DataFrame


# Calendar dimension (Dunnes retail calendar)
SQL_CALENDERS = """
SELECT
  CalendarKey,
  Dunnes_Year,
  Dunnes_Week,
  Start_Date,
  End_Date,
  ISO_Week_Start,
  ISO_Week_End,
  ISO_Year
FROM CFG.Calenders;
"""

# Optional: pack sizes to convert EPOS units -> replenishment cases
SQL_PACK_SIZES = """
SELECT
  Dynamics_Code,
  Units_Per_Case,
  Case_Multiple
FROM CFG.ReplenishmentPack;
"""

def load_base(ttl: int = 300) -> EposBase:
    latest = qdf(SQL_LATEST_WEEK, ttl=ttl)
    store_weekly = qdf(SQL_STORE_WEEKLY, ttl=ttl)
    product_weekly = qdf(SQL_PRODUCT_WEEKLY, ttl=ttl)

    for df in (latest, store_weekly, product_weekly):
        if "Start_Date" in df.columns:
            df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
        if "End_Date" in df.columns:
            df["End_Date"] = pd.to_datetime(df["End_Date"], errors="coerce")
        if "CalendarKey" in df.columns:
            df["CalendarKey"] = df["CalendarKey"].astype(str)

    return EposBase(latest=latest, store_weekly=store_weekly, product_weekly=product_weekly)

def week_dimension(store_weekly: pd.DataFrame) -> pd.DataFrame:
    if store_weekly.empty:
        return pd.DataFrame(columns=["CalendarKey","Start_Date","Dunnes_Year","Dunnes_Week"])
    d = store_weekly.dropna(subset=["Start_Date"]).drop_duplicates(subset=["CalendarKey"]).copy()
    cols = [c for c in ["CalendarKey","Start_Date","Dunnes_Year","Dunnes_Week"] if c in d.columns]
    return d[cols].sort_values("Start_Date")

def latest_key(base: EposBase) -> Optional[str]:
    if not base.latest.empty and "CalendarKey" in base.latest.columns:
        return str(base.latest.iloc[0]["CalendarKey"])
    d = week_dimension(base.store_weekly)
    return str(d.iloc[-1]["CalendarKey"]) if not d.empty else None

def calendar_dimension(ttl: int = 3600) -> pd.DataFrame:
    """Load Dunnes calendar dimension from CFG.Calenders.

    We intentionally use this table for the Week dropdown so week labels stay in sync
    across year boundaries (e.g., Dunnes week 1 may start in late December).
    """
    df = qdf(SQL_CALENDERS, ttl=ttl)
    if df.empty:
        return df
    df = df.copy()
    df["CalendarKey"] = df["CalendarKey"].astype(str)
    df["Start_Date"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    df["End_Date"] = pd.to_datetime(df["End_Date"], errors="coerce")
    df["Dunnes_Year"] = pd.to_numeric(df["Dunnes_Year"], errors="coerce").astype("Int64")
    df["Dunnes_Week"] = pd.to_numeric(df["Dunnes_Week"], errors="coerce").astype("Int64")
    return df.sort_values(["Start_Date", "CalendarKey"]).reset_index(drop=True)


def load_pack_sizes(ttl: int = 3600) -> pd.DataFrame:
    """Load product case pack sizes if CFG.ReplenishmentPack exists.

    If the table does not exist yet, callers should catch exceptions or handle empty df.
    """
    try:
        df = qdf(SQL_PACK_SIZES, ttl=ttl)
    except Exception:
        return pd.DataFrame(columns=["Dynamics_Code", "Units_Per_Case", "Case_Multiple"])
    if df.empty:
        return pd.DataFrame(columns=["Dynamics_Code", "Units_Per_Case", "Case_Multiple"])
    df = df.copy()
    df["Dynamics_Code"] = df["Dynamics_Code"].astype(str)
    df["Units_Per_Case"] = pd.to_numeric(df["Units_Per_Case"], errors="coerce").fillna(1).astype(int)
    if "Case_Multiple" in df.columns:
        df["Case_Multiple"] = pd.to_numeric(df["Case_Multiple"], errors="coerce").fillna(1).astype(int)
    else:
        df["Case_Multiple"] = 1
    return df
