from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Tuple

from ..config import load_settings
from ..db import get_conn

def _core_db_name() -> str:
    s = load_settings()
    if not s.core_db:
        raise RuntimeError("CORE_DB (or Core_DB) environment variable is not set.")
    return s.core_db

def fetch_object_counts() -> Dict[str, int]:
    sql = """
    SELECT
        SUM(CASE WHEN o.type = 'U' THEN 1 ELSE 0 END) AS tables_count,
        SUM(CASE WHEN o.type = 'V' THEN 1 ELSE 0 END) AS views_count,
        SUM(CASE WHEN o.type = 'P' THEN 1 ELSE 0 END) AS procs_count
    FROM sys.objects o
    WHERE o.is_ms_shipped = 0;
    """
    with get_conn(database=_core_db_name()) as conn:
        row = conn.cursor().execute(sql).fetchone()
    return {"tables": int(row[0] or 0), "views": int(row[1] or 0), "procs": int(row[2] or 0)}

@lru_cache(maxsize=1)
def fetch_table_list() -> List[str]:
    sql = """
    SELECT s.name AS schema_name, t.name AS table_name
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.is_ms_shipped = 0
    ORDER BY s.name, t.name;
    """
    with get_conn(database=_core_db_name()) as conn:
        rows = conn.cursor().execute(sql).fetchall()
    return [f"{r[0]}.{r[1]}" for r in rows]

def fetch_top_tables(limit: int = 10) -> List[Dict[str, Any]]:
    sql = f"""
    SELECT TOP ({limit})
        QUOTENAME(s.name) + '.' + QUOTENAME(t.name) AS table_name,
        SUM(p.rows) AS row_count
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    JOIN sys.partitions p ON p.object_id = t.object_id
    WHERE p.index_id IN (0,1)
      AND t.is_ms_shipped = 0
    GROUP BY s.name, t.name
    ORDER BY row_count DESC;
    """
    with get_conn(database=_core_db_name()) as conn:
        rows = conn.cursor().execute(sql).fetchall()
    return [{"table": r[0], "rows": int(r[1] or 0)} for r in rows]

def fetch_table_preview(full_name: str, limit: int = 100) -> Tuple[List[str], List[Dict[str, Any]]]:
    allowed = set(fetch_table_list())
    if full_name not in allowed:
        raise ValueError("Invalid table selection.")

    schema, table = full_name.split(".", 1)
    sql = f"SELECT TOP ({limit}) * FROM [{schema}].[{table}];"

    with get_conn(database=_core_db_name()) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    data = [dict(zip(cols, r)) for r in rows]
    return cols, data
