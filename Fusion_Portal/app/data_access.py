from __future__ import annotations

from typing import List, Optional

from .db import get_conn
from .user_model import User

def fetch_user_by_username_or_email(login: str) -> Optional[dict]:
    sql = """
    SELECT TOP 1 user_id, username, email, password_hash, first_name, last_name, role, is_active
    FROM ADM.Users
    WHERE username = ? OR email = ?
    """
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(sql, login, login).fetchone()
        cur.close()
    if not row:
        return None
    cols = ["user_id","username","email","password_hash","first_name","last_name","role","is_active"]
    return dict(zip(cols, row))

def fetch_user_by_id(user_id: int) -> Optional[User]:
    sql = """
    SELECT user_id, username, email, first_name, last_name, role, is_active
    FROM ADM.Users
    WHERE user_id = ?
    """
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(sql, user_id).fetchone()
        cur.close()
    if not row:
        return None
    return User(
        user_id=row[0],
        username=row[1],
        email=row[2],
        first_name=row[3],
        last_name=row[4],
        role=row[5],
        is_active=bool(row[6]),
    )

def update_last_login(user_id: int) -> None:
    sql = "UPDATE ADM.Users SET last_login = SYSDATETIME() WHERE user_id = ?"
    with get_conn(autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(sql, user_id)
        cur.close()

def fetch_user_profile(user_id: int) -> dict:
    sql = """
    SELECT theme, default_module, landing_layout, kpi_preferences
    FROM ADM.UserProfile
    WHERE user_id = ?
    """
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(sql, user_id).fetchone()
        cur.close()

    if not row:
        return {"theme":"light","default_module":None,"landing_layout":None,"kpi_preferences":None}

    return {
        "theme": row[0],
        "default_module": row[1],
        "landing_layout": row[2],
        "kpi_preferences": row[3],
    }

def fetch_modules_for_user(user_id: int) -> List[dict]:
    sql = """
    SELECT m.module_name, m.module_url, m.icon
    FROM ADM.Modules m
    INNER JOIN ADM.UserModuleAccess a ON a.module_id = m.module_id
    WHERE a.user_id = ? AND a.can_view = 1 AND m.is_active = 1
    ORDER BY m.module_name
    """
    with get_conn() as conn:
        cur = conn.cursor()
        rows = cur.execute(sql, user_id).fetchall()
        cur.close()

    return [{"name": r[0], "url": r[1], "icon": r[2]} for r in rows]

def user_can_access_url(user_id: int, module_url: str) -> bool:
    # Accept URLs with or without trailing slash
    url1 = module_url.rstrip("/")
    url2 = url1 + "/"

    sql = """
    SELECT TOP 1 1
    FROM ADM.Modules m
    INNER JOIN ADM.UserModuleAccess a ON a.module_id = m.module_id
    WHERE a.user_id = ?
      AND a.can_view = 1
      AND m.is_active = 1
      AND (m.module_url = ? OR m.module_url = ?)
    """
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(sql, user_id, url1, url2).fetchone()
        cur.close()
    return bool(row)

def fetch_kpis_for_user(user_id: int) -> List[dict]:
    # Stub KPIs. Replace with real queries later.
    return [
        {"title": "Active Projects", "value": "14", "hint": "Demo KPI - wire to Projects table"},
        {"title": "Budget Variance", "value": "€1.2M", "hint": "Demo KPI - wire to Finance module"},
        {"title": "Open Risks", "value": "8", "hint": "Demo KPI - wire to Risk register"},
        {"title": "Delivery Score", "value": "92%", "hint": "Demo KPI - computed metric"},
    ]
