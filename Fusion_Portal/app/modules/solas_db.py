# solas_db.py
# ----------
# DB access helpers for the Solas Live Dashboard.
#
# Notes:
# - This code expects SQL Server tables similar to the Solas export.
# - Credentials are read from an INI file; they NEVER go to the browser.
# - Uses pyodbc (ODBC Driver 17/18 recommended).

from __future__ import annotations

import configparser
import datetime as _dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd


@dataclass(frozen=True)
class DbParams:
    driver: str
    server: str
    database: str
    user: str = ""
    password: str = ""
    encrypt: str = "yes"
    trust_server_certificate: str = "no"


def read_ini(ini_path: Path) -> DbParams:
    cfg = configparser.ConfigParser()
    with open(ini_path, "r", encoding="utf-8") as f:
        cfg.read_file(f)
    if "database" not in cfg:
        raise ValueError("INI missing [database] section.")
    db = cfg["database"]
    return DbParams(
        driver=db.get("driver", "{ODBC Driver 17 for SQL Server}"),
        server=db["server"],
        database=db["database"],
        user=db.get("user", ""),
        password=db.get("password", ""),
        encrypt=db.get("encrypt", "yes"),
        trust_server_certificate=db.get("trust_server_certificate", "no"),
    )


def connect_db(params: DbParams):
    try:
        import pyodbc  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "pyodbc is not installed. Install it first (pip install pyodbc) "
            "and make sure an ODBC SQL Server driver is installed."
        ) from e

    parts = [
        f"DRIVER={params.driver}",
        f"SERVER={params.server}",
        f"DATABASE={params.database}",
        f"Encrypt={params.encrypt}",
        f"TrustServerCertificate={params.trust_server_certificate}",
    ]
    if params.user:
        parts.append(f"UID={params.user}")
    if params.password:
        parts.append(f"PWD={params.password}")

    conn_str = ";".join(parts)
    return pyodbc.connect(conn_str)


def table_exists(conn, schema: str, table: str) -> bool:
    sql = "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?"
    cur = conn.cursor()
    cur.execute(sql, (schema, table))
    row = cur.fetchone()
    cur.close()
    return row is not None


def safe_read_sql(conn, sql: str, params=None) -> pd.DataFrame:
    try:
        return pd.read_sql(sql, conn, params=params)
    except Exception as e:
        print(f"[WARN] Query failed: {e}\nSQL: {sql[:250]}...", file=sys.stderr)
        return pd.DataFrame()


def month_floor(d: _dt.date) -> _dt.date:
    return _dt.date(d.year, d.month, 1)


def month_ceil_exclusive(d: _dt.date) -> _dt.date:
    # first day of next month
    if d.month == 12:
        return _dt.date(d.year + 1, 1, 1)
    return _dt.date(d.year, d.month + 1, 1)


def fetch_dimensions(conn, schema: str) -> Dict[str, pd.DataFrame]:
    """
    Loads dimension-style tables. These are small and good candidates for caching.
    """
    dims: Dict[str, pd.DataFrame] = {}

    # activities (include description + client/type/status/priority so we can layer analysis)
    if table_exists(conn, schema, "activities"):
        dims["activities"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              activity_code,
              title,
              description,
              status_id,
              type_id,
              priority_id,
              parent_id,
              client_id,
              sharepoint_link,
              da_relevant
            FROM {schema}.activities;
            """,
        )
    else:
        dims["activities"] = pd.DataFrame()

    # resources
    if table_exists(conn, schema, "resources"):
        dims["resources"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              service_provider_id,
              first_name,
              surname,
              email_address,
              location_id,
              role_rate_id,
              application_role_name,
              in_active,
              employment_type_id,
              default_approver_id
            FROM {schema}.resources;
            """,
        )
    else:
        dims["resources"] = pd.DataFrame()

    # clients
    if table_exists(conn, schema, "clients"):
        dims["clients"] = safe_read_sql(conn, f"SELECT id, name, status FROM {schema}.clients;")
    else:
        dims["clients"] = pd.DataFrame()

    # activity types/status/priorities
    for key, tbl, cols in [
        ("activity_types", "activity_types", "id, title"),
        ("activity_statuses", "activity_statuses", "id, title"),
        ("activity_priorities", "activity_priorities", "id, title"),
    ]:
        if table_exists(conn, schema, tbl):
            dims[key] = safe_read_sql(conn, f"SELECT {cols} FROM {schema}.{tbl};")
        else:
            dims[key] = pd.DataFrame()

    # teams (optional) + resource_teams bridge
    if table_exists(conn, schema, "teams"):
        dims["teams"] = safe_read_sql(conn, f"SELECT id, title, description FROM {schema}.teams;")
    else:
        dims["teams"] = pd.DataFrame()

    if table_exists(conn, schema, "resource_teams"):
        dims["resource_teams"] = safe_read_sql(conn, f"SELECT resource_id, team_id FROM {schema}.resource_teams;")
    else:
        dims["resource_teams"] = pd.DataFrame()

    return dims


def fetch_facts(conn, schema: str, start: _dt.date, end_exclusive: _dt.date) -> Dict[str, pd.DataFrame]:
    """
    Loads fact-style tables filtered to the selected date window.
    end_exclusive is exclusive (like SQL >= start AND < end_exclusive).
    """
    facts: Dict[str, pd.DataFrame] = {}

    # Activity actuals (hours, daily)
    if table_exists(conn, schema, "activity_resource_actuals"):
        facts["actuals"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              resource_id,
              activity_id,
              [date],
              hours,
              comment,
              approved,
              created_date,
              approved_by,
              approved_on,
              activity_status_at_time_of_record
            FROM {schema}.activity_resource_actuals
            WHERE [date] >= ? AND [date] < ?;
            """,
            params=[start, end_exclusive],
        )
    else:
        facts["actuals"] = pd.DataFrame()

    # Support actuals (hours_spent, daily)
    if table_exists(conn, schema, "support_resource_actuals"):
        facts["support"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              resource_id,
              ticket_number,
              ticket_description,
              [date],
              hours_spent,
              comment,
              approved,
              created_date,
              approved_by,
              approved_on
            FROM {schema}.support_resource_actuals
            WHERE [date] >= ? AND [date] < ?;
            """,
            params=[start, end_exclusive],
        )
    else:
        facts["support"] = pd.DataFrame()

    # Leave actuals (amount in DAYS, daily)
    if table_exists(conn, schema, "leave_resource_actuals"):
        facts["leave"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              resource_id,
              leave_id,
              [date],
              amount,
              comment,
              create_date,
              approved_by,
              approved_on
            FROM {schema}.leave_resource_actuals
            WHERE [date] >= ? AND [date] < ?;
            """,
            params=[start, end_exclusive],
        )
    else:
        facts["leave"] = pd.DataFrame()

    # Forecasts (monthly, allocation_days) — filter by month range overlapping the date window
    month_start = month_floor(start)
    month_end_excl = month_ceil_exclusive(end_exclusive - _dt.timedelta(days=1))
    if table_exists(conn, schema, "activity_resource_forecasts"):
        facts["forecasts"] = safe_read_sql(
            conn,
            f"""
            SELECT
              id,
              resource_id,
              activity_id,
              month_year,
              allocation_days
            FROM {schema}.activity_resource_forecasts
            WHERE month_year >= ? AND month_year < ?;
            """,
            params=[month_start, month_end_excl],
        )
    else:
        facts["forecasts"] = pd.DataFrame()

    return facts

# Convenience: override only the database name (useful when server/user/etc are shared)
def with_database(params: DbParams, database: str) -> DbParams:
    return DbParams(
        driver=params.driver,
        server=params.server,
        database=database,
        user=params.user,
        password=params.password,
        encrypt=params.encrypt,
        trust_server_certificate=params.trust_server_certificate,
    )
