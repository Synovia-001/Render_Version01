# solas_transform.py
# ------------------
# Turns Solas raw tables into analytics-friendly frames:
# - Normalises units (everything in HOURS)
# - Builds week/month period keys
# - Explodes monthly forecast (days) into daily hours for correct weekly rollups
#
# The goal: make reporting logic explicit and reusable.

from __future__ import annotations

import datetime as _dt
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


HOURS_PER_DAY = 8.0


def _to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _week_start(d: pd.Series) -> pd.Series:
    # Monday as week start
    dt = pd.to_datetime(d, errors="coerce")
    return (dt - pd.to_timedelta(dt.dt.weekday, unit="D")).dt.normalize()


def add_period(df: pd.DataFrame, date_col: str, grain: str) -> pd.DataFrame:
    out = df.copy()
    out[date_col] = _to_datetime(out[date_col])
    if grain == "month":
        out["period"] = out[date_col].dt.to_period("M").astype(str)
    else:
        out["period"] = _week_start(out[date_col]).dt.date.astype(str)
    return out


def build_resource_label(resources: pd.DataFrame) -> pd.DataFrame:
    r = resources.copy()
    r["first_name"] = r.get("first_name", "").fillna("").astype(str)
    r["surname"] = r.get("surname", "").fillna("").astype(str)
    r["ResourceLabel"] = (r["first_name"] + " " + r["surname"]).str.strip() + " [" + r["id"].astype(str) + "]"
    return r


def build_activity_label(activities: pd.DataFrame) -> pd.DataFrame:
    a = activities.copy()
    a["activity_code"] = a.get("activity_code", "").fillna("").astype(str)
    a["title"] = a.get("title", "").fillna("").astype(str)
    a["ActivityLabel"] = np.where(a["activity_code"].str.strip() != "", a["activity_code"], a["title"])
    return a


def attach_activity_dims(activities: pd.DataFrame, dims: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    a = activities.copy()

    if "clients" in dims and not dims["clients"].empty and "client_id" in a.columns:
        a = a.merge(dims["clients"][["id", "name"]].rename(columns={"id": "client_id", "name": "client_name"}),
                    on="client_id", how="left")
    else:
        a["client_name"] = np.nan

    if "activity_types" in dims and not dims["activity_types"].empty and "type_id" in a.columns:
        a = a.merge(dims["activity_types"][["id", "title"]].rename(columns={"id": "type_id", "title": "type_title"}),
                    on="type_id", how="left")
    else:
        a["type_title"] = np.nan

    if "activity_statuses" in dims and not dims["activity_statuses"].empty and "status_id" in a.columns:
        a = a.merge(dims["activity_statuses"][["id", "title"]].rename(columns={"id": "status_id", "title": "status_title"}),
                    on="status_id", how="left")
    else:
        a["status_title"] = np.nan

    if "activity_priorities" in dims and not dims["activity_priorities"].empty and "priority_id" in a.columns:
        a = a.merge(dims["activity_priorities"][["id", "title"]].rename(columns={"id": "priority_id", "title": "priority_title"}),
                    on="priority_id", how="left")
    else:
        a["priority_title"] = np.nan

    return a


def filter_resources_by_team(resources: pd.DataFrame, dims: Dict[str, pd.DataFrame], team_id: Optional[str]) -> pd.DataFrame:
    if not team_id:
        return resources
    if "resource_teams" not in dims or dims["resource_teams"].empty:
        return resources.iloc[0:0]  # nothing matches if we can't map
    rt = dims["resource_teams"].copy()
    rt["team_id"] = rt["team_id"].astype(str)
    keep_ids = set(rt.loc[rt["team_id"] == str(team_id), "resource_id"].astype(int).tolist())
    return resources[resources["id"].isin(keep_ids)].copy()


def explode_monthly_forecast_to_daily(forecasts: pd.DataFrame, start: _dt.date, end_exclusive: _dt.date) -> pd.DataFrame:
    """
    Input: forecasts with month_year + allocation_days (days/month/resource/activity)
    Output: daily rows with forecast_hours distributed evenly across business days for that month.
    """
    if forecasts.empty:
        return pd.DataFrame(columns=["date", "resource_id", "activity_id", "forecast_hours"])

    f = forecasts.copy()
    f["month_year"] = pd.to_datetime(f["month_year"], errors="coerce")
    f["allocation_days"] = pd.to_numeric(f.get("allocation_days", 0), errors="coerce").fillna(0.0)
    f["forecast_hours_month"] = f["allocation_days"] * HOURS_PER_DAY

    rows = []
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end_exclusive)

    for _, row in f.iterrows():
        m = row["month_year"]
        if pd.isna(m):
            continue
        m_start = pd.Timestamp(year=int(m.year), month=int(m.month), day=1)
        m_end = (m_start + pd.offsets.MonthBegin(1))  # first day next month
        # intersect with selected range
        rng_start = max(m_start, start_ts)
        rng_end = min(m_end, end_ts)
        if rng_start >= rng_end:
            continue

        bdays = pd.bdate_range(rng_start, rng_end - pd.Timedelta(days=1))
        if len(bdays) == 0:
            continue
        per_day = float(row["forecast_hours_month"]) / float(len(pd.bdate_range(m_start, m_end - pd.Timedelta(days=1))))
        # distribute using full-month business day count, not range count, to keep totals consistent
        # then only keep the overlapping business days
        for d in bdays:
            rows.append({
                "date": d.normalize(),
                "resource_id": int(row["resource_id"]),
                "activity_id": int(row["activity_id"]),
                "forecast_hours": per_day,
            })

    return pd.DataFrame(rows)


def build_unified_frames(
    dims: Dict[str, pd.DataFrame],
    facts: Dict[str, pd.DataFrame],
    start: _dt.date,
    end_exclusive: _dt.date,
    grain: str,
    team_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    client_id: Optional[str] = None,
    type_id: Optional[str] = None,
    status_id: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Returns a dict of cleaned / joined frames ready for charting + tables.
    """
    activities = build_activity_label(dims.get("activities", pd.DataFrame()))
    activities = attach_activity_dims(activities, dims)
    resources = build_resource_label(dims.get("resources", pd.DataFrame()))

    # filter resource set by team
    resources_f = filter_resources_by_team(resources, dims, team_id)

    if resource_id:
        resources_f = resources_f[resources_f["id"].astype(str) == str(resource_id)].copy()

    # active flag if present
    if "in_active" in resources_f.columns:
        # in_active appears to be 1 for active in your export; keep both for now, but mark
        resources_f["is_active"] = pd.to_numeric(resources_f["in_active"], errors="coerce").fillna(1).astype(int) == 1
    else:
        resources_f["is_active"] = True

    # filter activity set by client/type/status
    activities_f = activities.copy()
    if client_id and "client_id" in activities_f.columns:
        activities_f = activities_f[activities_f["client_id"].astype(str) == str(client_id)].copy()
    if type_id and "type_id" in activities_f.columns:
        activities_f = activities_f[activities_f["type_id"].astype(str) == str(type_id)].copy()
    if status_id and "status_id" in activities_f.columns:
        activities_f = activities_f[activities_f["status_id"].astype(str) == str(status_id)].copy()

    keep_resource_ids = set(resources_f["id"].astype(int).tolist())
    keep_activity_ids = set(activities_f["id"].astype(int).tolist())

    # --- Actual activity hours ---
    actuals = facts.get("actuals", pd.DataFrame()).copy()
    if not actuals.empty:
        actuals["date"] = _to_datetime(actuals["date"])
        actuals["hours"] = pd.to_numeric(actuals.get("hours", 0), errors="coerce").fillna(0.0)
        actuals = actuals[actuals["resource_id"].astype(int).isin(keep_resource_ids)]
        actuals = actuals[actuals["activity_id"].astype(int).isin(keep_activity_ids)]
        actuals = actuals.merge(resources_f[["id", "ResourceLabel"]].rename(columns={"id":"resource_id"}),
                                on="resource_id", how="left")                          .merge(activities_f[["id","activity_code","title","description","ActivityLabel","client_name","type_title","status_title","priority_title"]].rename(columns={"id":"activity_id"}),
                                on="activity_id", how="left")
        actuals = add_period(actuals, "date", grain)
    else:
        actuals = pd.DataFrame(columns=["date","hours","resource_id","activity_id","ResourceLabel","ActivityLabel","period"])

    # --- Support hours ---
    support = facts.get("support", pd.DataFrame()).copy()
    if not support.empty:
        support["date"] = _to_datetime(support["date"])
        support["hours_spent"] = pd.to_numeric(support.get("hours_spent", 0), errors="coerce").fillna(0.0)
        support = support[support["resource_id"].astype(int).isin(keep_resource_ids)]
        support = support.merge(resources_f[["id", "ResourceLabel"]].rename(columns={"id":"resource_id"}),
                                on="resource_id", how="left")
        support = add_period(support, "date", grain)
    else:
        support = pd.DataFrame(columns=["date","hours_spent","resource_id","ResourceLabel","period"])

    # --- Leave hours (days -> hours) ---
    leave = facts.get("leave", pd.DataFrame()).copy()
    if not leave.empty:
        leave["date"] = _to_datetime(leave["date"])
        leave["amount"] = pd.to_numeric(leave.get("amount", 0), errors="coerce").fillna(0.0)
        leave["leave_hours"] = leave["amount"] * HOURS_PER_DAY
        leave = leave[leave["resource_id"].astype(int).isin(keep_resource_ids)]
        leave = leave.merge(resources_f[["id", "ResourceLabel"]].rename(columns={"id":"resource_id"}),
                            on="resource_id", how="left")
        leave = add_period(leave, "date", grain)
    else:
        leave = pd.DataFrame(columns=["date","leave_hours","resource_id","ResourceLabel","period"])

    # --- Forecast hours (monthly days -> daily hours -> period hours) ---
    forecasts = facts.get("forecasts", pd.DataFrame()).copy()
    if not forecasts.empty:
        forecasts = forecasts[forecasts["resource_id"].astype(int).isin(keep_resource_ids)]
        forecasts = forecasts[forecasts["activity_id"].astype(int).isin(keep_activity_ids)]
        daily = explode_monthly_forecast_to_daily(forecasts, start, end_exclusive)
        if not daily.empty:
            daily = daily.merge(resources_f[["id", "ResourceLabel"]].rename(columns={"id":"resource_id"}),
                                on="resource_id", how="left")                          .merge(activities_f[["id","ActivityLabel"]].rename(columns={"id":"activity_id"}),
                                on="activity_id", how="left")
            daily = add_period(daily, "date", grain)
        else:
            daily = pd.DataFrame(columns=["date","resource_id","activity_id","forecast_hours","period"])
    else:
        daily = pd.DataFrame(columns=["date","resource_id","activity_id","forecast_hours","period"])

    return {
        "resources": resources_f,
        "activities": activities_f,
        "actuals": actuals,
        "support": support,
        "leave": leave,
        "forecast_daily": daily,
    }