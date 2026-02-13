import pyodbc
from .config import load_settings

pyodbc.pooling = True

PREFERRED_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
]

def _pick_driver(requested: str) -> str:
    available = pyodbc.drivers()
    requested = (requested or "").strip()

    if requested in available:
        return requested

    for cand in PREFERRED_DRIVERS:
        if cand in available:
            return cand

    raise RuntimeError(f"No suitable SQL Server ODBC driver found. Available={available}")

def conn_str(database: str | None = None) -> str:
    s = load_settings()
    driver = _pick_driver(s.db_driver)

    db = database or s.db_database

    missing = [k for k, v in {
        "DB_SERVER": s.db_server,
        "DB_USER": s.db_user,
        "DB_PASSWORD": s.db_password,
        "DATABASE": db
    }.items() if not v]

    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}")

    # No secrets in logs
    print(f"[DB] Using ODBC driver: {driver} | Database: {db}")

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={s.db_server};"
        f"DATABASE={db};"
        f"UID={s.db_user};"
        f"PWD={s.db_password};"
        f"Encrypt={s.db_encrypt};"
        f"TrustServerCertificate={s.db_trust_server_certificate};"
        "Connection Timeout=30;"
    )

def get_conn(autocommit: bool = False, database: str | None = None):
    return pyodbc.connect(conn_str(database=database), autocommit=autocommit)
