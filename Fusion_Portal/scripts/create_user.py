import argparse
import os
from getpass import getpass
from pathlib import Path

import pyodbc
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def load_conn_str() -> str:
    driver = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE", "Fusion_Dashboard")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    encrypt = os.getenv("DB_ENCRYPT", "yes")
    trust = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "no")

    ini_path = os.getenv("FUSION_INI_PATH")
    if not ini_path:
        default_ini = Path(__file__).resolve().parents[1] / "config" / "Fusion_Dashboard.ini"
        if default_ini.exists():
            ini_path = str(default_ini)

    if ini_path and Path(ini_path).exists():
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        db = cfg["database"]
        driver = db.get("driver", driver)
        server = db.get("server", server)
        database = db.get("database", database)
        user = db.get("user", user)
        password = db.get("password", password)
        encrypt = db.get("encrypt", encrypt)
        trust = db.get("trust_server_certificate", trust)
        driver = driver.strip()
        if driver.startswith("{") and driver.endswith("}"):
            driver = driver[1:-1]

    missing = [k for k, v in {"DB_SERVER": server, "DB_USER": user, "DB_PASSWORD": password}.items() if not v]
    if missing:
        raise SystemExit(f"Missing required DB settings: {', '.join(missing)}")

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
        "Connection Timeout=30;"
    )

def main():
    ap = argparse.ArgumentParser(description="Create a portal user in ADM.Users (bcrypt hash).")
    ap.add_argument("--username", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--first", default=None)
    ap.add_argument("--last", default=None)
    ap.add_argument("--role", default="User")
    ap.add_argument("--inactive", action="store_true")
    args = ap.parse_args()

    pw1 = getpass("Password: ")
    pw2 = getpass("Confirm: ")
    if pw1 != pw2:
        raise SystemExit("Passwords do not match.")

    password_hash = pwd_context.hash(pw1)
    is_active = 0 if args.inactive else 1

    conn_str = load_conn_str()
    with pyodbc.connect(conn_str, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ADM.Users (username, email, password_hash, first_name, last_name, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            args.username, args.email, password_hash, args.first, args.last, args.role, is_active
        )
        cur.close()

    print("User created successfully.")

if __name__ == "__main__":
    main()
