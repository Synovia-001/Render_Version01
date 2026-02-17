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
