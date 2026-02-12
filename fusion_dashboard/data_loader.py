import datetime as dt
from functools import lru_cache

import pandas as pd
import numpy as np

from config import load_settings

RUNDETAIL_SQL = r"""
SELECT
    rd.DetailID,
    rd.RunID,
    rd.MovementCode,
    rd.InterfaceCode,
    rd.Principal_Code,
    p.Principal AS PrincipalName,
    im.Interface AS InterfaceName,
    im.Type AS InterfaceType,
    im.Profile AS InterfaceProfile,
    im.Direction AS ConfigDirection,
    rd.Direction AS RunDirection,
    rd.FileName,
    rd.SourcePath,
    rd.DestinationPath,
    rd.FileSizeBytes,
    rd.Status,
    rd.ErrorMessage,
    rd.StartTime,
    rd.EndTime
FROM LOG.RunDetail rd
LEFT JOIN REF.Principals p
    ON rd.Principal_Code = p.Principal_Code
LEFT JOIN CFG.Interface_Movements im
    ON rd.InterfaceCode = im.InterfaceCode
   AND rd.MovementCode = im.MovementCode
   AND rd.Principal_Code = im.Principal_Code
WHERE rd.StartTime >= ?
  AND rd.StartTime < ?
"""

EXPECTED_SQL = r"""
SELECT
    InterfaceCode,
    Principal_Code,
    MovementCode,
    Variant,
    Type,
    Profile,
    Interface,
    Direction,
    FilePattern,
    File_Mask,
    Source,
    Destination,
    Active
FROM CFG.Interface_Movements
WHERE Active = 1
"""

MONTHS_SQL = r"""
SELECT DISTINCT CONVERT(char(7), StartTime, 120) AS MonthKey
FROM LOG.RunDetail
WHERE StartTime IS NOT NULL
ORDER BY MonthKey DESC
"""

def month_to_range(month_str: str):
    """month_str 'YYYY-MM' -> [start, end)"""
    y, m = month_str.split("-")
    year = int(y); month = int(m)
    start = dt.datetime(year, month, 1)
    end = dt.datetime(year + (1 if month == 12 else 0), (1 if month == 12 else month + 1), 1)
    return start, end

def _pick_driver(preferred: str = "") -> str:
    """
    Picks an ODBC driver name.
    If ODBC_DRIVER is set, uses that.
    Else tries Driver 18 then 17.
    """
    if preferred:
        return preferred

    try:
        import pyodbc
        drivers = [d for d in pyodbc.drivers()]
    except Exception:
        # fallback – may still fail later, but gives a clearer message
        return "ODBC Driver 18 for SQL Server"

    for cand in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]:
        if cand in drivers:
            return cand

    # Return something helpful
    return drivers[-1] if drivers else "ODBC Driver 18 for SQL Server"

def _conn():
    s = load_settings()
    missing = [k for k in ["DB_SERVER","DB_NAME","DB_USER","DB_PASSWORD"] if not s.get(k)]
    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}. Set env vars (Render) or render.ini (local).")

    driver = _pick_driver(s.get("ODBC_DRIVER","").strip())
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={s['DB_SERVER']};"
        f"DATABASE={s['DB_NAME']};"
        f"UID={s['DB_USER']};"
        f"PWD={s['DB_PASSWORD']};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    try:
        import pyodbc
    except Exception as e:
        raise RuntimeError("pyodbc not installed. pip install pyodbc") from e

    return pyodbc.connect(conn_str)

def list_available_months() -> list[str]:
    conn = _conn()
    try:
        months = pd.read_sql(MONTHS_SQL, conn)["MonthKey"].dropna().astype(str).tolist()
    finally:
        conn.close()
    return months

@lru_cache(maxsize=1)
def load_cfg_active() -> pd.DataFrame:
    conn = _conn()
    try:
        cfg = pd.read_sql(EXPECTED_SQL, conn)
    finally:
        conn.close()

    if cfg.empty:
        return cfg

    # Normalize types
    cfg["MovementCode"] = cfg["MovementCode"].astype(str)
    cfg["InterfaceCode"] = cfg["InterfaceCode"].astype(str)
    cfg["Principal_Code"] = cfg["Principal_Code"].astype(str)

    # Friendly labels
    cfg["PrincipalLabel"] = cfg["Principal_Code"]
    cfg["InterfaceLabel"] = cfg["Interface"].fillna(cfg["InterfaceCode"]).astype(str) + " (" + cfg["InterfaceCode"].astype(str) + ")"

    return cfg

def _derive_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    df["MovementCode"] = df["MovementCode"].astype(str)
    df["InterfaceCode"] = df["InterfaceCode"].astype(str)
    df["Principal_Code"] = df["Principal_Code"].astype(str)

    df["PrincipalName"] = df["PrincipalName"].fillna(df["Principal_Code"]).astype(str)
    df["InterfaceName"] = df["InterfaceName"].fillna(df["InterfaceCode"]).astype(str)

    df["StatusNorm"] = df["Status"].astype(str).str.strip().str.upper()
    df["IsSuccess"] = df["StatusNorm"].isin(["SUCCESS", "SUCCEEDED", "OK", "COMPLETED", "SUCCESSFUL", "SUCCESS "])

    df["FileSizeBytes"] = pd.to_numeric(df["FileSizeBytes"], errors="coerce").fillna(0).astype(float)

    df["StartTime"] = pd.to_datetime(df["StartTime"], errors="coerce")
    df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")

    df["StartDate"] = df["StartTime"].dt.date.astype(str)
    df["StartHour"] = df["StartTime"].dt.hour

    df["DurationSeconds"] = (df["EndTime"] - df["StartTime"]).dt.total_seconds()
    df.loc[df["DurationSeconds"] < 0, "DurationSeconds"] = np.nan

    df["ErrorMessageClean"] = df["ErrorMessage"].fillna("").astype(str).str.strip()
    df.loc[df["ErrorMessageClean"] == "", "ErrorMessageClean"] = "(none)"

    df["InProgress"] = df["EndTime"].isna()

    return df

def build_expected_map(cfg_active: pd.DataFrame) -> pd.DataFrame:
    if cfg_active.empty:
        return pd.DataFrame(columns=["Principal_Code","InterfaceCode","ExpectedMovementList","ExpectedMovementCount"])

    df = cfg_active.copy()
    grp = df.groupby(["Principal_Code", "InterfaceCode"], dropna=False)["MovementCode"]
    out = grp.apply(lambda s: sorted(set(s.tolist()))).reset_index(name="ExpectedMovementList")
    out["ExpectedMovementCount"] = out["ExpectedMovementList"].apply(len)
    return out

def compute_route_completeness(run_df: pd.DataFrame, expected_map_df: pd.DataFrame) -> pd.DataFrame:
    """
    Route = (Principal_Code, InterfaceCode) configured in CFG.
    A "Route Run" = (RunID, Principal_Code, InterfaceCode) observed in LOG.
    """
    if run_df.empty:
        return pd.DataFrame(columns=[
            "RunID","Principal_Code","InterfaceCode",
            "ActualMovementCount","ExpectedMovementCount",
            "CompletenessRatio","RouteStatus"
        ])

    actual = (
        run_df.groupby(["RunID","Principal_Code","InterfaceCode"], dropna=False)["MovementCode"]
        .nunique()
        .reset_index(name="ActualMovementCount")
    )

    merged = actual.merge(
        expected_map_df[["Principal_Code","InterfaceCode","ExpectedMovementCount"]],
        on=["Principal_Code","InterfaceCode"],
        how="left"
    )
    merged["CompletenessRatio"] = merged["ActualMovementCount"] / merged["ExpectedMovementCount"]

    merged["RouteStatus"] = np.where(
        merged["ExpectedMovementCount"].isna(),
        "UNKNOWN",
        np.where(
            merged["ActualMovementCount"] >= merged["ExpectedMovementCount"],
            "COMPLETE",
            "INCOMPLETE"
        )
    )
    return merged

@lru_cache(maxsize=24)
def load_month(month: str) -> dict:
    """
    Loads a month of RunDetail plus precomputed completeness.
    Cached by month for snappy filtering.
    """
    start, end = month_to_range(month)

    conn = _conn()
    try:
        run = pd.read_sql(RUNDETAIL_SQL, conn, params=[start, end])
    finally:
        conn.close()

    run = _derive_fields(run)

    cfg = load_cfg_active()
    exp_map = build_expected_map(cfg)
    completeness = compute_route_completeness(run, exp_map)

    # Add friendly names to completeness rows
    if not run.empty and not completeness.empty:
        dim = (
            run.groupby(["Principal_Code","InterfaceCode"], dropna=False)
            .agg(PrincipalName=("PrincipalName","first"), InterfaceName=("InterfaceName","first"))
            .reset_index()
        )
        completeness = completeness.merge(dim, on=["Principal_Code","InterfaceCode"], how="left")

    return {
        "month": month,
        "run": run,
        "cfg": cfg,
        "expected_map": exp_map,
        "completeness": completeness,
    }