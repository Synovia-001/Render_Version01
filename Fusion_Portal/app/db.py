import pyodbc
from .config import load_settings

# Enable pyodbc pooling (helps performance)
pyodbc.pooling = True

def conn_str() -> str:
    s = load_settings()
    missing = [k for k, v in {"DB_SERVER": s.db_server, "DB_USER": s.db_user, "DB_PASSWORD": s.db_password}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}")

    return (
        f"DRIVER={{{s.db_driver}}};"
        f"SERVER={s.db_server};"
        f"DATABASE={s.db_database};"
        f"UID={s.db_user};"
        f"PWD={s.db_password};"
        f"Encrypt={s.db_encrypt};"
        f"TrustServerCertificate={s.db_trust_server_certificate};"
        "Connection Timeout=30;"
    )

def get_conn(autocommit: bool = False):
    return pyodbc.connect(conn_str(), autocommit=autocommit)
